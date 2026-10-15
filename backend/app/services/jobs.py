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
from app.schemas import TrackInfoOut, TrackingParamsIn
from app.science.periods import AnalysisError
from app.science.pipeline import track_with_segments
from app.science.synthetic import SyntheticPendulum, render_video
from app.science.tracking import VideoError
from app.services.segments import replace_auto_segments
from app.services.video_processing import (
    TRACK_FILE,
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

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _set(self, video_id: int, **values: object) -> None:
        with self._sessions() as session:
            session.execute(update(Video).where(Video.id == video_id).values(**values))
            session.commit()

    def _render_then_run(self, video_id: int, spec: SyntheticPendulum) -> None:
        folder = video_dir(self._videos_root, video_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "original.mp4"
        try:
            render_video(spec, path)
        except Exception:
            log.exception("Rendering of demo video %s failed", video_id)
            self._set(
                video_id, status=VideoStatus.FAILED, error="Не удалось сгенерировать демо-видео."
            )
            return
        self._set(video_id, size_bytes=path.stat().st_size)
        self._run(video_id)

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
            start = params.t_start or 0.0
            end = params.t_end or video.duration_s
            expected_frames = int(max(end - start, 0) * video.fps_nominal) or video.frame_count

        (folder / TRACK_FILE).unlink(missing_ok=True)
        try:
            track, found, axis = track_with_segments(
                source,
                to_tracking_params(params),
                axis=params.axis,
                progress=lambda p: self._set(video_id, progress=min(p, 0.99)),
                total_frames=expected_frames,
            )
            # Траекторию сохраняем до анализа: даже если колебаний не нашлось, по графику
            # x(t) будет видно, что пошло не так (потеря груза, неудачная обрезка и т. п.).
            write_track_csv(folder / TRACK_FILE, track)
        except (VideoError, AnalysisError) as exc:
            self._set(video_id, status=VideoStatus.FAILED, error=str(exc))
            return
        except Exception:
            log.exception("Tracking of video %s crashed", video_id)
            self._set(
                video_id,
                status=VideoStatus.FAILED,
                error="Внутренняя ошибка обработки, подробности в логе сервера.",
            )
            return

        with self._sessions() as session:
            video = session.get(Video, video_id)
            if video is None:  # видео удалили во время обработки
                return
            video.timing = timing_out(track).model_dump()
            video.track_info = TrackInfoOut(
                axis=axis,  # type: ignore[arg-type]
                detection_rate=track.detection_rate,
                frames=int(track.t.size),
            ).model_dump()
            replace_auto_segments(video, found, (track.t, track.x, track.y))
            if found:
                video.status, video.error = VideoStatus.DONE, None
            else:
                video.status = VideoStatus.FAILED
                video.error = (
                    "Не найдено ни одного участка регулярных колебаний (нужно хотя бы 4 "
                    "колебания подряд). Проверьте график движения: виден ли груз, не "
                    "мешают ли руки, верна ли область поиска."
                )
            video.progress = 1.0
            video.processed_at = datetime.now(UTC)
            session.commit()
