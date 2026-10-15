import csv
import io
import sqlite3

import pytest

from app.db import SCHEMA_VERSION, prepare_sqlite_file
from app.science.synthetic import SyntheticPendulum, render_video
from tests.conftest import wait_for_videos


@pytest.fixture
def experiment(client):
    return client.post("/api/experiments", json={"name": "Тест", "g_reference": 9.81}).json()


@pytest.fixture
def series(client, experiment):
    resp = client.post(
        f"/api/experiments/{experiment['id']}/series",
        json={"length_cm": 50, "length_sigma_cm": 0.2},
    )
    assert resp.status_code == 201
    return resp.json()


def upload(client, experiment_id, path, series_id=None):
    data = {"series_id": str(series_id)} if series_id else None
    with path.open("rb") as fh:
        return client.post(
            f"/api/experiments/{experiment_id}/videos",
            files={"file": (path.name, fh, "video/mp4")},
            data=data,
        )


def test_health_and_unknown_api_route(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/does-not-exist").status_code == 404


def test_stopwatch_statistics_and_outlier_flag(client, experiment, series):
    times = [14.21, 14.18, 14.27, 14.20, 14.24, 14.19, 15.62, 14.22]  # 15.62 — сбился со счёта
    for t in times:
        resp = client.post(
            f"/api/series/{series['id']}/trials", json={"periods": 10, "total_time_s": t}
        )
        assert resp.status_code == 201

    detail = client.get(f"/api/series/{series['id']}").json()
    flagged = [t["total_time_s"] for t in detail["trials"] if t["suspected_outlier"]]
    assert flagged == [15.62]

    outlier_id = next(t["id"] for t in detail["trials"] if t["suspected_outlier"])
    client.patch(f"/api/trials/{outlier_id}", json={"excluded": True})

    analysis = client.get(f"/api/experiments/{experiment['id']}/analysis").json()
    sw = analysis["series"][0]["stopwatch"]
    assert sw["summary"]["n"] == 7 and sw["excluded"] == 1
    assert sw["summary"]["mean"] == pytest.approx(1.4216, abs=1e-3)
    assert analysis["series"][0]["camera"] is None
    assert analysis["conclusions"]


def test_validation_errors(client, experiment, series, tmp_path):
    bad_length = client.post(f"/api/experiments/{experiment['id']}/series", json={"length_cm": -1})
    assert bad_length.status_code == 422
    (tmp_path / "notes.txt").write_text("hello")
    assert upload(client, experiment["id"], tmp_path / "notes.txt").status_code == 415
    (tmp_path / "broken.mp4").write_bytes(b"not a video")
    assert upload(client, experiment["id"], tmp_path / "broken.mp4").status_code == 422
    assert client.get(f"/api/experiments/{experiment['id']}").json()["videos"] == []
    color_without_color = {"method": "color"}
    resp = client.post("/api/videos/999/track", json=color_without_color)
    assert resp.status_code == 422


def test_full_video_pipeline(client, experiment, series, tmp_path):
    spec = SyntheticPendulum(length_m=0.5, amplitude_deg=12, duration_s=14, hold_s=2)
    render_video(spec, tmp_path / "clip.mp4")
    resp = upload(client, experiment["id"], tmp_path / "clip.mp4", series_id=series["id"])
    assert resp.status_code == 201, resp.text
    video = resp.json()
    assert video["width"] == spec.width and video["fps_nominal"] == pytest.approx(60)
    assert video["preferred_series_id"] == series["id"]

    frame = client.get(f"/api/videos/{video['id']}/frame", params={"t": 0, "max_width": 320})
    assert frame.headers["content-type"] == "image/jpeg"

    params = {"method": "motion", "min_area": 30}
    preview = client.post(
        f"/api/videos/{video['id']}/preview", json={"time_s": 6, "params": params}
    ).json()
    assert preview["found"]

    assert client.post(f"/api/videos/{video['id']}/track", json=params).status_code == 200
    (done,) = wait_for_videos(client, [video["id"]])
    assert done["status"] == "done", done["error"]
    assert done["track_info"]["axis"] == "x"
    (segment,) = done["segments"]
    assert segment["series_id"] == series["id"]  # единственный участок — к длине загрузки
    assert segment["t_start"] == pytest.approx(spec.hold_s, abs=0.6)
    result = segment["result"]
    assert result["length_px_source"] == "arc"  # точку подвеса нашли по дуге
    assert result["theta_max_deg"] == pytest.approx(12, abs=1.5)
    assert result["t0"] == pytest.approx(2 * 3.141592653589793 * (0.5 / 9.81) ** 0.5, rel=1e-3)

    # Масштаб и подвес применяются без повторного трекинга.
    scale = {"p1": {"x": 0, "y": 0}, "p2": {"x": 100, "y": 0}, "distance_cm": 10}
    geo = client.put(f"/api/videos/{video['id']}/geometry", json={"scale": scale}).json()
    assert geo["params"]["scale"]["distance_cm"] == 10
    assert geo["segments"][0]["result"]["px_per_cm"] == pytest.approx(10)
    assert geo["segments"][0]["result"]["length_from_video_cm"] is not None

    track = client.get(f"/api/videos/{video['id']}/track").json()
    assert len(track["t"]) == done["track_info"]["frames"]
    assert client.get(f"/api/videos/{video['id']}/track.csv").status_code == 200

    # Ручная правка границ пересчитывает результат по сохранённой траектории.
    narrowed = client.patch(
        f"/api/segments/{segment['id']}", json={"t_start": 5.0, "t_end": 11.0}
    ).json()
    assert narrowed["auto"] is False
    assert narrowed["result"]["periods_observed"] < result["periods_observed"]
    manual = client.post(
        f"/api/videos/{video['id']}/segments", json={"t_start": 11.0, "t_end": 13.9}
    ).json()
    assert manual["series_id"] is None and manual["result"] is not None

    for t in (14.21, 14.18, 14.27, 14.20, 14.24):
        client.post(f"/api/series/{series['id']}/trials", json={"periods": 10, "total_time_s": t})
    row = client.get(f"/api/experiments/{experiment['id']}/analysis").json()["series"][0]
    assert row["camera"]["segments"] == 1
    assert row["camera"]["t0"]["value"] == pytest.approx(row["theory"]["t0"], rel=1e-3)
    assert row["camera_vs_theory"]["compared"] == "t0"
    assert row["comparison"]["spread_ratio"] > 3

    # Удаление длины не удаляет видео — участок просто отвязывается.
    assert client.delete(f"/api/series/{series['id']}").status_code == 204
    again = client.get(f"/api/videos/{video['id']}").json()
    assert all(s["series_id"] is None for s in again["segments"])

    assert client.delete(f"/api/segments/{manual['id']}").status_code == 204
    assert client.delete(f"/api/videos/{video['id']}").status_code == 204
    assert client.get(f"/api/videos/{video['id']}").status_code == 404


def test_demo_experiment_end_to_end(client):
    demo = client.post("/api/experiments/demo").json()
    detail = client.get(f"/api/experiments/{demo['id']}").json()
    video_ids = [v["id"] for v in detail["videos"]]
    videos = wait_for_videos(client, video_ids, timeout=180)
    assert all(v["status"] == "done" for v in videos), [v["error"] for v in videos]
    assert all(len(v["segments"]) == 1 and v["segments"][0]["series_id"] for v in videos)

    # В демо есть замер, где «сбились со счёта»: программа помечает его, исключает человек.
    flagged = [t for s in detail["series"] for t in s["trials"] if t["suspected_outlier"]]
    assert len(flagged) == 1 and flagged[0]["total_time_s"] > 13
    client.patch(f"/api/trials/{flagged[0]['id']}", json={"excluded": True})

    analysis = client.get(f"/api/experiments/{demo['id']}/analysis").json()
    overall = analysis["overall"]
    assert overall["ratio"] > 10 and overall["p_value"] < 1e-3
    assert overall["stopwatch_event_sigma"] == pytest.approx(0.045, rel=0.35)

    fit = analysis["fit_camera"]
    assert fit["g"]["value"] == pytest.approx(9.81, rel=5e-3)
    # В демо длина «занижена» на 0,8 см — аппроксимация T²(L) должна это заметить.
    assert fit["length_offset_cm"]["value"] == pytest.approx(0.8, abs=0.3)

    assert any(r["short_cm"] == 20 and r["long_cm"] == 80 for r in analysis["ratios"])
    assert [p["periods"] for p in analysis["n_dependence"]["points"]] == [1, 5, 10, 20]
    assert len(analysis["conclusions"]) >= 3

    export = client.get(f"/api/experiments/{demo['id']}/export.csv")
    rows = list(csv.reader(io.StringIO(export.text.lstrip("﻿")), delimiter=";"))
    assert len(rows) == 1 + 6 and rows[0][0] == "L, см"
    assert len(rows[1]) == len(rows[0])

    assert client.delete(f"/api/experiments/{demo['id']}").status_code == 204


def test_outdated_database_is_backed_up(tmp_path):
    db = tmp_path / "pendulum.db"
    videos = tmp_path / "videos"
    (videos / "1").mkdir(parents=True)
    (videos / "1" / "track.csv").write_text("old")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE videos (id INTEGER)")
    prepare_sqlite_file(db, related=(videos,))
    assert not db.exists() and not videos.exists()  # старые файлы не смешаются с новыми id
    assert len(list(tmp_path.glob("pendulum.db.v0-*.bak"))) == 1
    assert len(list(tmp_path.glob("videos.v0-*.bak"))) == 1
    with sqlite3.connect(db) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    prepare_sqlite_file(db)  # актуальная версия — не трогаем
    assert db.exists()
