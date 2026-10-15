from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2
"""Меняется при несовместимом изменении таблиц. Миграций нет (локальная SQLite-база),
поэтому база старой версии не удаляется, а откладывается в .bak и создаётся заново."""


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # фоновый трекинг пишет, пока UI читает
        cursor.close()

    return engine


def _stored_version(path: Path) -> int | None:
    if not path.exists():
        return None
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as conn:
            return int(conn.execute(text("PRAGMA user_version")).scalar() or 0)
    finally:
        engine.dispose()


def prepare_sqlite_file(path: Path, related: tuple[Path, ...] = ()) -> None:
    """Отложить базу несовместимой версии в сторону, чтобы приложение стартовало чистым.

    related — каталоги, связанные с базой по id (загруженные видео): их тоже нужно отложить,
    иначе новая запись с тем же id попадёт в каталог со старыми файлами."""
    version = _stored_version(path)
    if version is None or version == SCHEMA_VERSION:
        return
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.v{version}-{stamp}.bak")
    for suffix in ("", "-wal", "-shm"):
        part = path.with_name(path.name + suffix)
        if part.exists():
            part.rename(backup.with_name(backup.name + suffix))
    for directory in related:
        if directory.exists():
            directory.rename(directory.with_name(f"{directory.name}.v{version}-{stamp}.bak"))
    log.warning("Database schema v%s is outdated; moved to %s", version, backup)


class Database:
    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from app import models  # noqa: F401 — регистрирует таблицы в metadata

        Base.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session
