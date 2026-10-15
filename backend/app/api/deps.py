from __future__ import annotations

import shutil
from collections.abc import Iterable, Iterator
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Database
from app.services.jobs import TrackingQueue
from app.services.video_processing import video_dir

T = TypeVar("T")


def get_db(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.db
    yield from database.session()


def get_queue(request: Request) -> TrackingQueue:
    return request.app.state.queue


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


DbSession = Annotated[Session, Depends(get_db)]
Queue = Annotated[TrackingQueue, Depends(get_queue)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_or_404(session: Session, model: type[T], obj_id: int, what: str) -> T:
    obj = session.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{what} не найден(о)")
    return obj


def remove_video_files(settings: Settings, video_ids: Iterable[int]) -> None:
    for video_id in video_ids:
        shutil.rmtree(video_dir(settings.videos_dir, video_id), ignore_errors=True)
