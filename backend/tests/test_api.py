import csv
import io
import math

import pytest

from app.science.synthetic import SyntheticPendulum, pivot_point, render_video
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


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


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


def test_validation_errors(client, experiment, series):
    assert (
        client.post(
            f"/api/experiments/{experiment['id']}/series", json={"length_cm": -1}
        ).status_code
        == 422
    )
    resp = client.post(
        f"/api/series/{series['id']}/videos", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 415
    resp = client.post(
        f"/api/series/{series['id']}/videos",
        files={"file": ("broken.mp4", b"not a video", "video/mp4")},
    )
    assert resp.status_code == 422
    assert client.get(f"/api/series/{series['id']}").json()["videos"] == []


def test_full_video_pipeline(client, experiment, series, tmp_path):
    spec = SyntheticPendulum(length_m=0.5, amplitude_deg=6, duration_s=10)
    truth = render_video(spec, tmp_path / "clip.mp4")
    with (tmp_path / "clip.mp4").open("rb") as fh:
        resp = client.post(
            f"/api/series/{series['id']}/videos", files={"file": ("clip.mp4", fh, "video/mp4")}
        )
    assert resp.status_code == 201, resp.text
    video = resp.json()
    assert video["width"] == spec.width and video["fps_nominal"] == pytest.approx(60)

    frame = client.get(f"/api/videos/{video['id']}/frame", params={"t": 0, "max_width": 320})
    assert frame.headers["content-type"] == "image/jpeg"

    x0, y0 = truth[0]
    color = client.post(
        f"/api/videos/{video['id']}/sample-color", json={"time_s": 0, "x": int(x0), "y": int(y0)}
    ).json()
    pivot_x, pivot_y = pivot_point(spec)
    params = {"color": color, "pivot": {"x": pivot_x, "y": pivot_y}, "t_start": 0.3}

    preview = client.post(
        f"/api/videos/{video['id']}/preview", json={"time_s": 0, "params": params}
    ).json()
    assert preview["found"] and preview["x"] == pytest.approx(x0, abs=0.5)

    assert client.post(f"/api/videos/{video['id']}/track", json=params).status_code == 200
    (done,) = wait_for_videos(client, [video["id"]])
    assert done["status"] == "done", done["error"]
    result = done["result"]
    assert result["detection_rate"] == 1.0
    assert result["amplitude_start_deg"] == pytest.approx(6, abs=0.3)
    assert done["timing"]["variable_frame_rate"] is False

    track = client.get(f"/api/videos/{video['id']}/track").json()
    assert len(track["t"]) == done["result"]["frames_analyzed"]
    assert client.get(f"/api/videos/{video['id']}/track.csv").status_code == 200

    for t in (14.21, 14.18, 14.27, 14.20, 14.24):
        client.post(f"/api/series/{series['id']}/trials", json={"periods": 10, "total_time_s": t})
    row = client.get(f"/api/experiments/{experiment['id']}/analysis").json()["series"][0]
    assert row["camera"]["period"]["value"] == pytest.approx(row["theory"]["t_corrected"], rel=1e-3)
    assert row["comparison"]["spread_ratio"] > 3

    assert client.delete(f"/api/videos/{video['id']}").status_code == 204
    assert client.get(f"/api/videos/{video['id']}").status_code == 404


def test_demo_experiment_end_to_end(client):
    demo = client.post("/api/experiments/demo").json()
    detail = client.get(f"/api/experiments/{demo['id']}").json()
    video_ids = [v["id"] for s in detail["series"] for v in s["videos"]]
    videos = wait_for_videos(client, video_ids, timeout=120)
    assert all(v["status"] == "done" for v in videos), [v["error"] for v in videos]

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
    assert not math.isnan(float(rows[1][8].replace(",", ".")))

    assert client.delete(f"/api/experiments/{demo['id']}").status_code == 204
