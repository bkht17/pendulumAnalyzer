from __future__ import annotations

import base64
import shutil
from dataclasses import asdict
from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import AppSettings, DbSession, Queue, get_or_404, remove_video_files
from app.api.serializers import video_out
from app.models import Series, Video, VideoStatus
from app.schemas import (
    ColorIn,
    PreviewIn,
    PreviewOut,
    RoiIn,
    SampleColorIn,
    TrackingParamsIn,
    TrackSeriesOut,
    VideoOut,
    VideoPatch,
)
from app.science.tracking import (
    Roi,
    VideoError,
    locate_marker,
    probe,
    read_frame_at,
    suggest_color_range,
)
from app.services.video_processing import (
    TRACK_FILE,
    read_track_csv,
    to_tracking_params,
    video_dir,
)

router = APIRouter(tags=["videos"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
CHUNK = 1024 * 1024


def _source(settings: AppSettings, video: Video) -> Path:
    return video_dir(settings.videos_dir, video.id) / video.stored_name


@router.post(
    "/series/{series_id}/videos", response_model=VideoOut, status_code=status.HTTP_201_CREATED
)
def upload_video(
    series_id: int, file: UploadFile, db: DbSession, settings: AppSettings
) -> VideoOut:
    series = get_or_404(db, Series, series_id, "Серия")
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
    )
    series.videos.append(video)
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


@router.post("/videos/{video_id}/preview", response_model=PreviewOut)
def preview_detection(
    video_id: int, payload: PreviewIn, db: DbSession, settings: AppSettings
) -> PreviewOut:
    """Проверка настроек на одном кадре: где найден маркер и как выглядит маска."""
    video = get_or_404(db, Video, video_id, "Видео")
    frame, _ = _read_frame(settings, video, payload.time_s)
    params = to_tracking_params(payload.params)
    detection, mask = locate_marker(frame, params)
    height, width = frame.shape[:2]
    roi = params.roi.clip(width, height) if params.roi else Roi(0, 0, width, height)
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
    return TrackSeriesOut(t=t, x=x, y=y)


@router.get("/videos/{video_id}/track.csv")
def download_track(video_id: int, db: DbSession, settings: AppSettings) -> FileResponse:
    video = get_or_404(db, Video, video_id, "Видео")
    path = video_dir(settings.videos_dir, video.id) / TRACK_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail="Траектория ещё не построена")
    stem = Path(video.original_name).stem
    return FileResponse(path, media_type="text/csv", filename=f"{stem}_track.csv")
