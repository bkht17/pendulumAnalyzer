from __future__ import annotations

import base64
import shutil
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import AppSettings, DbSession, Queue, get_or_404, remove_video_files
from app.api.serializers import segment_out, video_out
from app.models import Experiment, Video, VideoSegment, VideoStatus
from app.schemas import (
    ColorIn,
    GeometryIn,
    PreviewIn,
    PreviewOut,
    RoiIn,
    SampleColorIn,
    SegmentIn,
    SegmentOut,
    SegmentPatch,
    TrackingParamsIn,
    TrackSeriesOut,
    VideoOut,
    VideoPatch,
)
from app.science.tracking import (
    BackgroundModel,
    Roi,
    TrackingParams,
    VideoError,
    locate_marker,
    locate_moving,
    probe,
    quick_background,
    read_frame_at,
    suggest_color_range,
)
from app.services.segments import analyze_into, auto_assign, load_track, series_lengths
from app.services.video_processing import (
    TRACK_FILE,
    read_track_csv,
    to_tracking_params,
    video_dir,
)

router = APIRouter(tags=["videos"])

BOUNDS_TOLERANCE_S = 0.02
"""Правка границ меньше этого (округление в редакторе) не считается ручной."""
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
CHUNK = 1024 * 1024


def _source(settings: AppSettings, video: Video) -> Path:
    return video_dir(settings.videos_dir, video.id) / video.stored_name


@router.post(
    "/experiments/{experiment_id}/videos",
    response_model=VideoOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_video(
    experiment_id: int,
    file: UploadFile,
    db: DbSession,
    settings: AppSettings,
    series_id: Annotated[int | None, Form()] = None,
) -> VideoOut:
    """Видео загружается в эксперимент. series_id — длина, со страницы которой загружают:
    если в записи найдётся ровно одна серия колебаний, она будет привязана к этой длине."""
    experiment = get_or_404(db, Experiment, experiment_id, "Эксперимент")
    if series_id is not None and not any(s.id == series_id for s in experiment.series):
        raise HTTPException(status_code=422, detail="Эта длина не относится к эксперименту")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Формат {suffix or 'без расширения'} не поддерживается. "
            f"Допустимо: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    video = Video(
        original_name=file.filename or f"video{suffix}",
        stored_name=f"original{suffix}",
        size_bytes=0,
        width=0,
        height=0,
        fps_nominal=0,
        frame_count=0,
        duration_s=0,
        preferred_series_id=series_id,
    )
    experiment.videos.append(video)
    db.flush()  # нужен id для каталога

    folder = video_dir(settings.videos_dir, video.id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / video.stored_name
    limit = settings.max_upload_mb * CHUNK
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := file.file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status_code=413, detail=f"Файл больше {settings.max_upload_mb} МБ"
                    )
                out.write(chunk)
        info = probe(target)
    except VideoError as exc:
        db.rollback()
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BaseException:
        db.rollback()
        shutil.rmtree(folder, ignore_errors=True)
        raise

    video.size_bytes = size
    video.width, video.height = info.width, info.height
    video.fps_nominal, video.frame_count = info.fps_nominal, info.frame_count
    video.duration_s = info.duration
    db.commit()
    return video_out(video)


@router.get("/videos/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: DbSession) -> VideoOut:
    return video_out(get_or_404(db, Video, video_id, "Видео"))


@router.patch("/videos/{video_id}", response_model=VideoOut)
def update_video(video_id: int, payload: VideoPatch, db: DbSession) -> VideoOut:
    video = get_or_404(db, Video, video_id, "Видео")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(video, key, value)
    db.commit()
    return video_out(video)


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: int, db: DbSession, settings: AppSettings) -> Response:
    video = get_or_404(db, Video, video_id, "Видео")
    db.delete(video)
    db.commit()
    remove_video_files(settings, [video_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _read_frame(settings: AppSettings, video: Video, time_s: float):
    try:
        return read_frame_at(_source(settings, video), min(time_s, max(video.duration_s - 0.05, 0)))
    except VideoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/videos/{video_id}/frame",
    responses={200: {"content": {"image/jpeg": {}}}},
    response_class=Response,
)
def get_frame(
    video_id: int,
    db: DbSession,
    settings: AppSettings,
    t: float = Query(0.0, ge=0),
    max_width: int = Query(1280, ge=160, le=4096),
) -> Response:
    """Кадр для разметки. Клиент пересчитывает клики в пиксели исходного видео сам."""
    video = get_or_404(db, Video, video_id, "Видео")
    frame, actual = _read_frame(settings, video, t)
    height, width = frame.shape[:2]
    if width > max_width:
        frame = cv2.resize(frame, (max_width, round(height * max_width / width)), cv2.INTER_AREA)
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось закодировать кадр")
    return Response(
        content=jpeg.tobytes(),
        media_type="image/jpeg",
        headers={"X-Frame-Time": f"{actual:.6f}", "Cache-Control": "private, max-age=3600"},
    )


@router.post("/videos/{video_id}/sample-color", response_model=ColorIn)
def sample_color(
    video_id: int, payload: SampleColorIn, db: DbSession, settings: AppSettings
) -> ColorIn:
    video = get_or_404(db, Video, video_id, "Видео")
    frame, _ = _read_frame(settings, video, payload.time_s)
    try:
        color = suggest_color_range(frame, payload.x, payload.y, payload.radius)
    except VideoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ColorIn(**asdict(color))


_BACKGROUND_CACHE: OrderedDict[tuple, BackgroundModel] = OrderedDict()
_BACKGROUND_CACHE_SIZE = 6
_cache_lock = Lock()


def _preview_background(path: Path, video_id: int, params: TrackingParams, time_s: float):
    """Фон для предпросмотра строится по ±4 с вокруг кадра; кэшируется, чтобы перетаскивание
    ползунков не пересчитывало его каждый раз."""
    key = (video_id, params.roi, params.polarity, params.motion_threshold, round(time_s / 4))
    with _cache_lock:
        if key in _BACKGROUND_CACHE:
            _BACKGROUND_CACHE.move_to_end(key)
            return _BACKGROUND_CACHE[key]
    background = quick_background(path, params, time_s)
    with _cache_lock:
        _BACKGROUND_CACHE[key] = background
        while len(_BACKGROUND_CACHE) > _BACKGROUND_CACHE_SIZE:
            _BACKGROUND_CACHE.popitem(last=False)
    return background


@router.post("/videos/{video_id}/preview", response_model=PreviewOut)
def preview_detection(
    video_id: int, payload: PreviewIn, db: DbSession, settings: AppSettings
) -> PreviewOut:
    """Проверка настроек на одном кадре: где найден груз и как выглядит маска."""
    video = get_or_404(db, Video, video_id, "Видео")
    frame, actual = _read_frame(settings, video, payload.time_s)
    params = to_tracking_params(payload.params)
    try:
        if params.method == "motion":
            background = _preview_background(_source(settings, video), video.id, params, actual)
            detection, mask = locate_moving(frame, background, actual, params)
            roi = background.roi
        else:
            detection, mask = locate_marker(frame, params)
            height, width = frame.shape[:2]
            roi = params.roi.clip(width, height) if params.roi else Roi(0, 0, width, height)
    except VideoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ok, png = cv2.imencode(".png", mask)
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось закодировать маску")
    return PreviewOut(
        found=detection.found,
        x=detection.x if detection.found else None,
        y=detection.y if detection.found else None,
        area=detection.area,
        mask_png=base64.b64encode(png.tobytes()).decode("ascii"),
        roi=RoiIn(x=roi.x, y=roi.y, w=roi.w, h=roi.h),
    )


@router.post("/videos/{video_id}/track", response_model=VideoOut)
def start_tracking(
    video_id: int, payload: TrackingParamsIn, db: DbSession, queue: Queue
) -> VideoOut:
    video = get_or_404(db, Video, video_id, "Видео")
    if video.status in (VideoStatus.QUEUED, VideoStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Видео уже обрабатывается")
    video.params = payload.model_dump()
    video.status = VideoStatus.QUEUED
    video.progress = 0.0
    video.error = None
    db.commit()
    queue.submit(video.id)
    return video_out(video)


@router.get("/videos/{video_id}/track", response_model=TrackSeriesOut)
def get_track(video_id: int, db: DbSession, settings: AppSettings) -> TrackSeriesOut:
    video = get_or_404(db, Video, video_id, "Видео")
    path = video_dir(settings.videos_dir, video.id) / TRACK_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail="Траектория ещё не построена")
    t, x, y = read_track_csv(path)
    clean = lambda a: [None if np.isnan(v) else float(v) for v in a]  # noqa: E731
    return TrackSeriesOut(t=t.tolist(), x=clean(x), y=clean(y))


@router.get("/videos/{video_id}/track.csv")
def download_track(video_id: int, db: DbSession, settings: AppSettings) -> FileResponse:
    video = get_or_404(db, Video, video_id, "Видео")
    path = video_dir(settings.videos_dir, video.id) / TRACK_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail="Траектория ещё не построена")
    stem = Path(video.original_name).stem
    return FileResponse(path, media_type="text/csv", filename=f"{stem}_track.csv")


@router.post("/videos/{video_id}/auto-assign", response_model=VideoOut)
def auto_assign_segments(video_id: int, db: DbSession, settings: AppSettings) -> VideoOut:
    """Разложить непривязанные участки по длинам эксперимента по периоду."""
    video = get_or_404(db, Video, video_id, "Видео")
    auto_assign(video, _track_or_409(settings, video))
    db.commit()
    return video_out(video)


@router.put("/videos/{video_id}/geometry", response_model=VideoOut)
def update_geometry(
    video_id: int, payload: GeometryIn, db: DbSession, settings: AppSettings
) -> VideoOut:
    """Пересчёт всех участков с новой точкой подвеса и масштабом по сохранённой траектории."""
    video = get_or_404(db, Video, video_id, "Видео")
    track = _track_or_409(settings, video)
    video.params = {**(video.params or {}), **payload.model_dump()}
    lengths = series_lengths(video)
    for segment in video.segments:
        analyze_into(segment, video, track, lengths)
    db.commit()
    return video_out(video)


# --- Участки ---------------------------------------------------------------------------------


def _track_or_409(settings: AppSettings, video: Video):
    track = load_track(settings.videos_dir, video)
    if track is None or video.track_info is None:
        raise HTTPException(status_code=409, detail="Сначала обработайте видео")
    return track


def _check_series(video: Video, series_id: int | None) -> None:
    if series_id is not None and not any(s.id == series_id for s in video.experiment.series):
        raise HTTPException(status_code=422, detail="Эта длина не относится к эксперименту")


@router.post(
    "/videos/{video_id}/segments", response_model=SegmentOut, status_code=status.HTTP_201_CREATED
)
def create_segment(
    video_id: int, payload: SegmentIn, db: DbSession, settings: AppSettings
) -> SegmentOut:
    """Участок вручную — если автоматический поиск что-то пропустил или разрезал."""
    video = get_or_404(db, Video, video_id, "Видео")
    track = _track_or_409(settings, video)
    _check_series(video, payload.series_id)
    segment = VideoSegment(
        t_start=payload.t_start, t_end=payload.t_end, series_id=payload.series_id, auto=False
    )
    video.segments.append(segment)
    analyze_into(segment, video, track, series_lengths(video))
    db.commit()
    return segment_out(segment)


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
def update_segment(
    segment_id: int, payload: SegmentPatch, db: DbSession, settings: AppSettings
) -> SegmentOut:
    segment = get_or_404(db, VideoSegment, segment_id, "Участок")
    video = segment.video
    changes = payload.model_dump(exclude_unset=True)
    if "series_id" in changes:
        _check_series(video, changes["series_id"])
    t_start = changes.get("t_start", segment.t_start)
    t_end = changes.get("t_end", segment.t_end)
    if t_end <= t_start:
        raise HTTPException(status_code=422, detail="Конец участка должен быть позже начала")
    moved = (
        abs(t_start - segment.t_start) > BOUNDS_TOLERANCE_S
        or abs(t_end - segment.t_end) > BOUNDS_TOLERANCE_S
    )
    for key, value in changes.items():
        if key in ("t_start", "t_end") and not moved:
            continue  # те же границы (в т.ч. округлённые редактором) — ничего не меняем
        setattr(segment, key, value)
    if moved:
        segment.auto = False  # границы правил человек — при повторном трекинге не трогаем
    if moved or "series_id" in changes:
        analyze_into(segment, video, _track_or_409(settings, video), series_lengths(video))
    db.commit()
    return segment_out(segment)


@router.delete("/segments/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(segment_id: int, db: DbSession) -> Response:
    db.delete(get_or_404(db, VideoSegment, segment_id, "Участок"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
