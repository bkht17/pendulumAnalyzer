"""Фоновая обработка видео в пуле потоков.

OpenCV отпускает GIL во время декодирования и обработки кадров, поэтому потоков достаточно;
отдельный брокер задач (Celery/RQ) для локального однопользовательского приложения избыточен.
Статус и прогресс хранятся в БД — UI просто опрашивает видео.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.models import Video, VideoStatus
from app.schemas import TrackingParamsIn
from app.science.periods import AnalysisError
from app.science.synthetic import SyntheticPendulum, render_video
from app.science.tracking import VideoError, track_video
from app.services.video_processing import (
    TRACK_FILE,
    analyze_track,
    timing_out,
    to_tracking_params,
    video_dir,
    write_track_csv,
)

log = logging.getLogger(__name__)


class TrackingQueue:
    def __init__(
        self, session_factory: sessionmaker[Session], videos_root: Path, workers: int
    ) -> None:
        self._sessions = session_factory
        self._videos_root = videos_root
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tracking")

    def recover_interrupted(self) -> None:
        """После перезапуска сервера незавершённые задачи помечаются как прерванные."""
        with self._sessions() as session:
            session.execute(
                update(Video)
                .where(Video.status.in_([VideoStatus.QUEUED, VideoStatus.PROCESSING]))
                .values(
                    status=VideoStatus.FAILED,
                    error="Обработка прервана перезапуском сервера — запустите её снова.",
                )
            )
            session.commit()

    def submit(self, video_id: int) -> None:
        self._executor.submit(self._run, video_id)

    def submit_synthetic(self, video_id: int, spec: SyntheticPendulum) -> None:
        """Демо: сначала сгенерировать видео, затем обработать его как обычное."""
        self._executor.submit(self._render_then_run, video_id, spec)

    def _render_then_run(self, video_id: int, spec: SyntheticPendulum) -> None:
        folder = video_dir(self._videos_root, video_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "original.mp4"
        try:
            render_video(spec, path)
        except Exception:
            log.exception("Rendering of demo video %s failed", video_id)
            with self._sessions() as session:
                session.execute(
                    update(Video)
                    .where(Video.id == video_id)
                    .values(status=VideoStatus.FAILED, error="Не удалось сгенерировать демо-видео.")
                )
                session.commit()
            return
        with self._sessions() as session:
            session.execute(
                update(Video).where(Video.id == video_id).values(size_bytes=path.stat().st_size)
            )
            session.commit()
        self._run(video_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _set_progress(self, video_id: int, value: float) -> None:
        with self._sessions() as session:
            session.execute(update(Video).where(Video.id == video_id).values(progress=value))
            session.commit()

    def _run(self, video_id: int) -> None:
        with self._sessions() as session:
            video = session.get(Video, video_id)
            if video is None or video.params is None:
                return
            video.status = VideoStatus.PROCESSING
            video.progress = 0.0
            video.error = None
            session.commit()
            params = TrackingParamsIn.model_validate(video.params)
            folder = video_dir(self._videos_root, video.id)
            source = folder / video.stored_name
            length_cm = video.series.length_cm
            expected_frames = video.frame_count
            if params.t_start or params.t_end:
                start = params.t_start or 0.0
                end = params.t_end or video.duration_s
                expected_frames = int(max(end - start, 0) * video.fps_nominal) or video.frame_count

        timing = result = None
        (folder / TRACK_FILE).unlink(missing_ok=True)
        try:
            track = track_video(
                source,
                to_tracking_params(params),
                progress=lambda p: self._set_progress(video_id, p),
                total_frames=expected_frames,
            )
            # Траекторию сохраняем до анализа: если период не найдётся, по графику x(t)
            # будет видно, что пошло не так (потеря маркера, неудачная обрезка и т. п.).
            write_track_csv(folder / TRACK_FILE, track)
            timing = timing_out(track).model_dump()
            result = analyze_track(track, params, length_cm).model_dump()
            status, error = VideoStatus.DONE, None
        except (VideoError, AnalysisError) as exc:
            status, error = VideoStatus.FAILED, str(exc)
        except Exception:
            log.exception("Tracking of video %s crashed", video_id)
            status, error = VideoStatus.FAILED, "Внутренняя ошибка обработки, подробности в логе."

        with self._sessions() as session:
            video = session.get(Video, video_id)
            if video is None:  # видео удалили во время обработки
                return
            video.status = status
            video.error = error
            video.progress = 1.0 if status is VideoStatus.DONE else video.progress
            video.timing = timing
            video.result = result
            video.processed_at = datetime.now(UTC)
            session.commit()
