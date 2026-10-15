import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        frontend_dist=tmp_path / "no-frontend",
        max_upload_mb=50,
        tracking_workers=2,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def wait_for_videos(client: TestClient, video_ids: list[int], timeout: float = 60) -> list[dict]:
    deadline = time.monotonic() + timeout
    while True:
        videos = [client.get(f"/api/videos/{vid}").json() for vid in video_ids]
        if all(v["status"] in ("done", "failed") for v in videos):
            return videos
        if time.monotonic() > deadline:
            raise TimeoutError([v["status"] for v in videos])
        time.sleep(0.2)
