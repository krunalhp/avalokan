import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from avalokan.api import create_app
from avalokan.contracts import AnalysisConfig
from avalokan.db import connect
from avalokan.engine import analyze, run_job
from avalokan.worker import recover


def upload(client, video):
    with video.open("rb") as file:
        response = client.post("/v1/media", files={"file": ("clip.mp4", file, "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()


def test_api_auth_limits_and_immutable_job_retry(settings, video, monkeypatch):
    settings.demo = False
    settings.token = "test-only-token-not-a-production-secret"
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/jobs").status_code == 401
        assert client.post("/v1/media", files={"file": ("x.mp4", b"invalid")}).status_code == 401
        assert client.post("/v1/session", json={"token": "wrong"}).status_code == 401
        assert client.post("/v1/session", json={"token": "गलत"}).status_code == 401
        login = client.post("/v1/session", json={"token": settings.token})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        assert "JobRecord" in schemas and "EventRecord" in schemas
        assert client.get("/v1/capabilities").json()["access_mode"] == "token"
        assert client.post("/v1/media", files={"file": ("x.mp4", b"invalid")}).status_code == 422
        media = upload(client, video)
        assert media["sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
        assert "path" not in media
        monkeypatch.setenv("AVALOKAN_ALLOWED_ACTIVITIES", "object.present")
        assert [a["id"] for a in client.get("/v1/capabilities").json()["activities"]] == [
            "object.present"
        ]
        assert (
            client.post(
                "/v1/jobs",
                json={"media_id": media["id"], "config": {"allowed_activities": ["zone.dwell"]}},
                headers={"Idempotency-Key": "instance-denied"},
            ).status_code
            == 422
        )
        body = {"media_id": media["id"], "config": {"allowed_activities": []}}
        assert client.post("/v1/jobs", json=body).status_code == 422
        headers = {"Idempotency-Key": "test-idempotency"}
        first = client.post("/v1/jobs", json=body, headers=headers)
        assert first.status_code == 202
        assert (
            client.post("/v1/jobs", json=body, headers=headers).json()["id"] == first.json()["id"]
        )
        body["config"]["sample_fps"] = 5
        assert client.post("/v1/jobs", json=body, headers=headers).status_code == 409
        assert (
            client.post(
                "/v1/jobs", json=body, headers=headers | {"Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )
        settings.max_upload = 100
        assert client.post("/v1/media", files={"file": ("x.mp4", b"x" * 101)}).status_code == 413
        assert (
            client.get(
                "/v1/events", params={"job_id": first.json()["id"], "from_s": 4, "to_s": 3}
            ).status_code
            == 422
        )
        client.delete("/v1/session")
        assert client.get(f"/v1/media/{media['id']}/video").status_code == 401
        assert (
            client.get(
                "/v1/jobs", headers={"Authorization": f"Bearer {settings.token}"}
            ).status_code
            == 200
        )


def test_source_time_sampling_and_no_dwell_across_gap(video):
    class PersonDetector:
        def detect(self, image, classes, threshold):
            return [("person", 0.8, (0.3, 0.2, 0.5, 0.6))]

    events, metrics, stats = analyze(
        video,
        "mov",
        AnalysisConfig(allowed_activities=["object.present", "zone.dwell"], dwell_seconds=2),
        PersonDetector(),
    )
    assert [round(m["time_s"], 2) for m in metrics] == [0, 0.5, 1, 1.5, 2, 4.5, 5]
    dwell = [e for e in events if e.activity == "zone.dwell"]
    assert [(e.start_s, e.end_s) for e in dwell] == [(0, 2)]
    assert stats["decoded_frames"] == stats["analyzed_frames"] == 7
    # A 5-second wall span must not become a 5-second supported dwell.
    assert len([e for e in events if e.activity == "object.present"]) == 2


def test_deny_all_job_recovery_atomic_result_and_video_ranges(settings, video):
    with TestClient(create_app(settings)) as client:
        media = upload(client, video)
        job = client.post(
            "/v1/jobs",
            json={"media_id": media["id"], "config": {"allowed_activities": []}},
            headers={"Idempotency-Key": "deny-all"},
        ).json()
        with connect(settings) as conn:
            conn.execute("UPDATE jobs SET status='running',attempts=1 WHERE id=%s", (job["id"],))
            recover(conn)
        assert client.get(f"/v1/jobs/{job['id']}").json()["status"] == "queued"
        with connect(settings) as conn:
            conn.execute("UPDATE jobs SET status='running',attempts=2 WHERE id=%s", (job["id"],))
        with pytest.raises(ValueError, match="publication"):
            run_job(settings, job["id"], expected_attempt=1)
        assert client.get(f"/v1/jobs/{job['id']}").json()["event_count"] == 0
        run_job(settings, job["id"], expected_attempt=2)
        complete = client.get(f"/v1/jobs/{job['id']}").json()
        assert (
            complete["status"],
            complete["event_count"],
            complete["stats"]["analyzed_frames"],
        ) == ("completed", 0, 0)
        assert client.get("/v1/events", params={"job_id": job["id"]}).json()["items"] == []
        ranged = client.get(f"/v1/media/{media['id']}/video", headers={"Range": "bytes=0-99"})
        assert ranged.status_code == 206 and len(ranged.content) == 100
        with pytest.raises(ValueError, match="publication"):
            run_job(settings, job["id"])
        assert client.get(f"/v1/jobs/{job['id']}").json()["status"] == "completed"


def test_event_overlap_pagination_and_append_only_review(settings, video):
    with TestClient(create_app(settings)) as client:
        media = upload(client, video)
        job = client.post(
            "/v1/jobs",
            json={"media_id": media["id"], "config": {"allowed_activities": []}},
            headers={"Idempotency-Key": "query"},
        ).json()
        ids = []
        with connect(settings) as conn:
            for start, end, activity in [
                (0, 2, "object.present"),
                (2, 2, "line.crossed"),
                (2, 5, "object.present"),
            ]:
                identity = uuid4()
                ids.append(str(identity))
                conn.execute(
                    """INSERT INTO events(id,job_id,activity,object_class,track_id,start_s,end_s,summary,
                    confidence,attributes,provenance) VALUES(%s,%s,%s,'person',1,%s,%s,'fixture',.8,%s,%s)""",
                    (identity, job["id"], activity, start, end, Jsonb({}), Jsonb({})),
                )
        query = {"job_id": job["id"], "from_s": 2, "to_s": 3, "limit": 1}
        first = client.get("/v1/events", params=query).json()
        assert [e["id"] for e in first["items"]] == [ids[1]]
        second = client.get("/v1/events", params=query | {"cursor": first["next_cursor"]}).json()
        assert [e["id"] for e in second["items"]] == [ids[2]] and second["next_cursor"] is None
        assert (
            client.get("/v1/events", params=query | {"object_class": "car"}).json()["items"] == []
        )
        for verdict in ["rejected", "uncertain"]:
            assert (
                client.post(
                    f"/v1/events/{ids[1]}/reviews", json={"verdict": verdict, "note": "test"}
                ).status_code
                == 201
            )
        detail = client.get(f"/v1/events/{ids[1]}").json()
        assert detail["review_status"] == "uncertain" and detail["summary"] == "fixture"
        assert [r["verdict"] for r in detail["reviews"]] == ["rejected", "uncertain"]


def test_url_ingest_validation_idempotency_and_polling(settings, monkeypatch):
    # Keep the ingest executor offline: the download step is exercised manually.
    monkeypatch.setattr("avalokan.ingest.download_media", lambda *args, **kwargs: None)
    with TestClient(create_app(settings)) as client:
        assert client.post(
            "/v1/media/url", json={"url": "ftp://example.com/clip.mp4"},
            headers={"Idempotency-Key": "ing-1"},
        ).status_code == 422

        first = client.post(
            "/v1/media/url", json={"url": "https://example.com/cctv.mp4"},
            headers={"Idempotency-Key": "ing-1"},
        )
        assert first.status_code == 202, first.text
        body = first.json()
        assert body["status"] == "downloading" and body["media"] is None and body["error"] is None

        again = client.post(
            "/v1/media/url", json={"url": "https://example.com/cctv.mp4"},
            headers={"Idempotency-Key": "ing-1"},
        )
        assert again.status_code == 202 and again.json()["id"] == body["id"]
        conflict = client.post(
            "/v1/media/url", json={"url": "https://example.com/other.mp4"},
            headers={"Idempotency-Key": "ing-1"},
        )
        assert conflict.status_code == 409

        assert client.get(f"/v1/media-ingests/{body['id']}").json()["url"] == "https://example.com/cctv.mp4"
        assert client.get("/v1/media-ingests/00000000-0000-0000-0000-000000000000").status_code == 404
