from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    frontend_dist: Path
    max_upload_mb: int
    tracking_workers: int

    @property
    def database_path(self) -> Path:
        return self.data_dir / "pendulum.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("PENDULUM_DATA_DIR", PROJECT_ROOT / "data")).resolve(),
        frontend_dist=Path(
            os.environ.get("PENDULUM_FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist")
        ).resolve(),
        max_upload_mb=int(os.environ.get("PENDULUM_MAX_UPLOAD_MB", "1024")),
        tracking_workers=int(os.environ.get("PENDULUM_TRACKING_WORKERS", "2")),
    )
