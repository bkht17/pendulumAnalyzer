from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Experiment(Base):
    """Серия опытов с общими настройками (место проведения → g, основное число периодов)."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    g_reference: Mapped[float] = mapped_column(default=9.81)
    main_periods: Mapped[int] = mapped_column(default=10)
    """Сколько колебаний отсчитывается секундомером в основной серии замеров."""
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    series: Mapped[list[Series]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="Series.length_cm",
    )
    videos: Mapped[list[Video]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="Video.id",
    )


class Series(Base):
    """Одна длина маятника и все измерения, сделанные при ней."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    length_cm: Mapped[float]
    length_sigma_cm: Mapped[float] = mapped_column(default=0.3)
    amplitude_deg: Mapped[float | None] = mapped_column(default=None)
    """Начальный угол отклонения, заданный вручную (если не измерен по видео)."""
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    experiment: Mapped[Experiment] = relationship(back_populates="series")
    trials: Mapped[list[StopwatchTrial]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="StopwatchTrial.id",
    )
    segments: Mapped[list[VideoSegment]] = relationship(
        back_populates="series",
        passive_deletes=True,
        order_by="VideoSegment.t_start",
    )


class StopwatchTrial(Base):
    __tablename__ = "stopwatch_trials"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    periods: Mapped[int]
    total_time_s: Mapped[float]
    operator: Mapped[str] = mapped_column(String(100), default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")
    """manual — введено вручную с внешнего секундомера, app — встроенный секундомер."""
    excluded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    series: Mapped[Series] = relationship(back_populates="trials")

    @property
    def period_s(self) -> float:
        return self.total_time_s / self.periods


class VideoStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Video(Base):
    """Видеофайл эксперимента. В одной записи может быть несколько серий (разные длины
    нити) — они хранятся как участки (VideoSegment) и привязываются к длинам по отдельности."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]
    fps_nominal: Mapped[float]
    frame_count: Mapped[int]
    duration_s: Mapped[float]
    preferred_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), default=None
    )
    """Длина, со страницы которой загрузили видео: ей отдаётся участок, если он один."""
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, native_enum=False, length=20), default=VideoStatus.UPLOADED
    )
    progress: Mapped[float] = mapped_column(default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    """Настройки трекинга: метод, цвет, область поиска, точка подвеса, масштаб, обрезка."""
    timing: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    track_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    """Сводка трекинга: ось колебаний, доля кадров с найденным грузом."""
    excluded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(default=None)

    experiment: Mapped[Experiment] = relationship(back_populates="videos")
    segments: Mapped[list[VideoSegment]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="VideoSegment.t_start",
    )


class VideoSegment(Base):
    """Участок свободных колебаний внутри видео — одна серия при одной длине нити."""

    __tablename__ = "video_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), default=None
    )
    t_start: Mapped[float]
    t_end: Mapped[float]
    auto: Mapped[bool] = mapped_column(default=True)
    """Найден автоматически (False — задан пользователем)."""
    excluded: Mapped[bool] = mapped_column(default=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    video: Mapped[Video] = relationship(back_populates="segments")
    series: Mapped[Series | None] = relationship(back_populates="segments")
