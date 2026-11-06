import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb

from . import ingest as ingest_module
from .activities import REGISTRY
from .contracts import (
    CLASSES,
    AnalysisConfig,
    EventDetail,
    EventRecord,
    IngestRecord,
    IngestRequest,
    JobList,
    JobRecord,
    JobRequest,
    MediaRecord,
    MetricSample,
    Page,
    ReviewRecord,
    ReviewRequest,
    SessionRequest,
)
from .db import EVENT_SELECT, JOB_SELECT, connect, migrate
from .media import FORMATS, probe
from .settings import MODEL_SHA256, ROOT, Settings
from .tracing import configure as configure_tracing
from .tracing import event as trace
from .tracing import new_trace_id


def required(row):
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def public_media(row):
    return {k: v for k, v in row.items() if k not in {"path", "playback_path", "format"}} | {
        "playback_ready": bool(row["playback_path"] and Path(row["playback_path"]).is_file())
    }


def page(rows, limit):
    more = len(rows) > limit
    rows = rows[:limit]
    cursor = str(rows[-1]["seq"]) if rows and more else None
    return {
        "items": [{k: v for k, v in row.items() if k != "seq"} for row in rows],
        "next_cursor": cursor,
    }


def create_app(settings=None):
    settings = settings or Settings()
    configure_tracing()
    ingest_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
    ingest_trace = new_trace_id("svc")

    @asynccontextmanager
    async def lifespan(app):
        if not settings.demo and len(settings.token) < 24:
            raise RuntimeError(
                "Set AVALOKAN_API_TOKEN (at least 24 characters) or explicitly enable AVALOKAN_DEMO=1"
            )
        settings.data.mkdir(parents=True, exist_ok=True)
        (settings.data / "media").mkdir(exist_ok=True)
        migrate(settings)
        trace(ingest_trace, "api.start", demo=settings.demo, pid=os.getpid())
        worker = None
        if os.getenv("AVALOKAN_WORKER") == "1":
            worker = subprocess.Popen([sys.executable, "-m", "avalokan.worker"])
        app.state.worker = worker
        try:
            yield
        finally:
            if worker:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()

    app = FastAPI(
        title="Avalokan CCTV workbench",
        version="0.1.0",
        lifespan=lifespan,
        description="Experimental sampled CCTV observations. Times are clip-relative seconds; no capture UTC or identity is inferred.",
    )

    def sign(expiry):
        return hmac.new(settings.token.encode(), expiry.encode(), "sha256").hexdigest()

    def authenticated(request):
        if settings.demo:
            return True
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer ") and secrets.compare_digest(
            authorization[7:].encode(), settings.token.encode()
        ):
            return True
        cookie = request.cookies.get("avalokan_session", "")
        try:
            expiry, signature = cookie.split(".", 1)
            return int(expiry) > time.time() and secrets.compare_digest(signature, sign(expiry))
        except (ValueError, TypeError):
            return False

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        trace_id = request.headers.get("x-trace-id") or new_trace_id("req")
        request.state.trace_id = trace_id
        started = time.perf_counter()
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("sec-fetch-site") == "cross-site"
        ):
            return JSONResponse({"detail": "Cross-site mutation refused"}, status_code=403)
        protected = path.startswith("/v1/") or path in {"/docs", "/openapi.json", "/redoc"}
        if protected and path != "/v1/session" and not authenticated(request):
            trace(trace_id, "http.unauthorized", method=request.method, path=path, level="warn")
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.headers.get("content-length")
            maximum = settings.max_upload + 1024 * 1024 if path == "/v1/media" else 16384
            try:
                if length is None:
                    return JSONResponse({"detail": "Content-Length required"}, status_code=411)
                if not 0 <= int(length) <= maximum:
                    trace(trace_id, "http.rejected", method=request.method, path=path,
                          detail="size limit", level="warn")
                    return JSONResponse({"detail": "Request exceeds size limit"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        trace(trace_id, "http.request", method=request.method, path=path,
              status=response.status_code, ms=int((time.perf_counter() - started) * 1000))
        response.headers["X-Content-Type-Options"] = "nosniff"
        if protected:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        worker = getattr(app.state, "worker", None)
        if worker and worker.poll() is not None:
            raise HTTPException(503, "Analysis worker stopped; restart the service")
        with connect(settings) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.post("/v1/session")
    def session(body: SessionRequest, request: Request, response: Response):
        if not settings.demo and not secrets.compare_digest(
            body.token.encode(), settings.token.encode()
        ):
            raise HTTPException(401, "Invalid token")
        expiry = str(int(time.time()) + 3600)
        response.set_cookie(
            "avalokan_session",
            f"{expiry}.{sign(expiry)}",
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=3600,
        )
        return {"authenticated": True}

    @app.delete("/v1/session", status_code=204)
    def logout(response: Response):
        response.delete_cookie("avalokan_session")

    @app.get("/v1/capabilities")
    def capabilities():
        return {
            "activities": [
                {"id": p.id, "name": p.name, "description": p.description, "status": "experimental"}
                for p in REGISTRY.values()
                if p.id in settings.allowed
            ],
            "classes": list(CLASSES.values()),
            "config_schema": AnalysisConfig.model_json_schema(),
            "model": {
                "name": "YOLOX Nano · CPU",
                "sha256": MODEL_SHA256,
                "ready": settings.model.is_file(),
            },
            "access_mode": "demo" if settings.demo else "token",
            "url_ingest": True,
            "max_upload_bytes": settings.max_upload,
            "max_duration_s": settings.max_duration,
        }

    @app.post("/v1/media", status_code=201, response_model=MediaRecord)
    def upload(request: Request, file: UploadFile = File(...)):
        name = Path((file.filename or "clip").replace("\\", "/")).name[:200]
        suffix = Path(name).suffix.lower()
        if suffix not in FORMATS:
            raise HTTPException(422, "Use MP4, MOV or MKV")
        identity = uuid4()
        target = settings.data / "media" / f"{identity}{suffix}"
        size, digest = 0, hashlib.sha256()
        try:
            with target.open("xb") as out:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload:
                        raise HTTPException(413, "Clip exceeds 250 MiB")
                    digest.update(chunk)
                    out.write(chunk)
            metadata = probe(target, FORMATS[suffix], settings.max_duration)
            with connect(settings) as conn:
                row = conn.execute(
                    """INSERT INTO media(id,name,path,format,duration_s,width,height,codec,size_bytes,sha256)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (
                        identity,
                        name,
                        str(target.resolve()),
                        FORMATS[suffix],
                        metadata["duration_s"],
                        metadata["width"],
                        metadata["height"],
                        metadata["codec"],
                        size,
                        digest.hexdigest(),
                    ),
                ).fetchone()
            trace(request.state.trace_id, "media.uploaded", media_id=str(identity),
                  name=name, size=size, duration_s=metadata["duration_s"])
            return public_media(row)
        except ValueError as exc:
            target.unlink(missing_ok=True)
            trace(request.state.trace_id, "media.upload.invalid", level="warn",
                  filename=name, error=str(exc))
            raise HTTPException(422, str(exc)) from exc
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()

    @app.post("/v1/media/url", status_code=202, response_model=IngestRecord)
    def ingest_url(body: IngestRequest, idempotency_key: str = Header(min_length=1, max_length=200)):
        """Fetch a remote video (YouTube and other sites) and ingest it as media."""
        trace_id = new_trace_id("ing")
        with connect(settings) as conn:
            conn.execute("SELECT pg_advisory_xact_lock(710203)")
            old = conn.execute(
                "SELECT id,url FROM media_ingests WHERE idempotency_key=%s", (idempotency_key,)
            ).fetchone()
            if old:
                if old["url"] != body.url:
                    raise HTTPException(
                        409, "Idempotency key was already used with different input"
                    )
                return ingest_record(conn, old["id"])
            pending = conn.execute(
                "SELECT count(*) AS n FROM media_ingests WHERE status='downloading'"
            ).fetchone()["n"]
            if pending >= 2:
                raise HTTPException(429, "Another download is in progress; try again shortly")
            identity = uuid4()
            conn.execute(
                "INSERT INTO media_ingests(id,url,idempotency_key) VALUES(%s,%s,%s)",
                (identity, body.url, idempotency_key),
            )
        trace(trace_id, "ingest.created", url=body.url, ingest_id=str(identity))
        ingest_pool.submit(ingest_module.download_media, settings, str(identity), body.url, trace_id)
        with connect(settings) as conn:
            return ingest_record(conn, identity)

    @app.get("/v1/media-ingests/{identity}", response_model=IngestRecord)
    def media_ingest(identity: UUID):
        with connect(settings) as conn:
            return ingest_record(conn, identity)

    def ingest_record(conn, identity) -> dict:
        row = required(
            conn.execute("SELECT * FROM media_ingests WHERE id=%s", (identity,)).fetchone()
        )
        media = None
        if row["media_id"]:
            media = conn.execute(
                "SELECT * FROM media WHERE id=%s", (row["media_id"],)
            ).fetchone()
        return {
            "id": row["id"],
            "url": row["url"],
            "status": row["status"],
            "error": row["error"],
            "media": public_media(media) if media else None,
            "created_at": row["created_at"],
        }

    @app.get("/v1/media/{identity}", response_model=MediaRecord)
    def media(identity: UUID):
        with connect(settings) as conn:
            return public_media(
                required(conn.execute("SELECT * FROM media WHERE id=%s", (identity,)).fetchone())
            )

    @app.get("/v1/media/{identity}/video")
    def video(identity: UUID):
        with connect(settings) as conn:
            row = required(conn.execute("SELECT * FROM media WHERE id=%s", (identity,)).fetchone())
        if not row["playback_path"] or not Path(row["playback_path"]).is_file():
            raise HTTPException(409, "Browser playback not ready; start analysis first")
        return FileResponse(row["playback_path"], media_type="video/mp4")

    @app.post("/v1/jobs", status_code=202, response_model=JobRecord)
    def submit(request: Request, body: JobRequest, idempotency_key: str = Header(min_length=1, max_length=200)):
        config = body.config.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        with connect(settings) as conn:
            # Serialize admission/idempotency checks, not analysis.
            conn.execute("SELECT pg_advisory_xact_lock(710202)")
            old = conn.execute(
                "SELECT id,request_hash FROM jobs WHERE idempotency_key=%s", (idempotency_key,)
            ).fetchone()
            if old:
                if old["request_hash"] != fingerprint:
                    raise HTTPException(
                        409, "Idempotency key was already used with different input"
                    )
                return conn.execute(JOB_SELECT + " WHERE j.id=%s", (old["id"],)).fetchone()
            required(conn.execute("SELECT id FROM media WHERE id=%s", (body.media_id,)).fetchone())
            if set(body.config.allowed_activities) - settings.allowed:
                raise HTTPException(422, "Activity is not allowed by this instance")
            if body.config.allowed_activities and not settings.model.is_file():
                raise HTTPException(
                    503, "Model not installed; run python -m avalokan.install_model"
                )
            pending = conn.execute(
                "SELECT count(*) AS n FROM jobs WHERE status IN ('queued','running')"
            ).fetchone()["n"]
            if pending >= 8:
                raise HTTPException(429, "Queue is full; wait for existing jobs")
            identity = uuid4()
            conn.execute(
                "INSERT INTO jobs(id,media_id,idempotency_key,request_hash,config) VALUES(%s,%s,%s,%s,%s)",
                (identity, body.media_id, idempotency_key, fingerprint, Jsonb(config)),
            )
            trace(request.state.trace_id, "job.submitted", job_id=str(identity),
                  media_id=str(body.media_id), config=config)
            return conn.execute(JOB_SELECT + " WHERE j.id=%s", (identity,)).fetchone()

    @app.get("/v1/jobs", response_model=JobList)
    def jobs(limit: int = Query(50, ge=1, le=100)):
        with connect(settings) as conn:
            return {
                "items": conn.execute(
                    JOB_SELECT + " ORDER BY j.created_at DESC,j.id DESC LIMIT %s", (limit,)
                ).fetchall()
            }

    @app.get("/v1/jobs/{identity}", response_model=JobRecord)
    def job(identity: UUID):
        with connect(settings) as conn:
            return required(conn.execute(JOB_SELECT + " WHERE j.id=%s", (identity,)).fetchone())

    @app.get("/v1/events", response_model=Page[EventRecord])
    def events(
        job_id: UUID,
        activity: str | None = None,
        object_class: str | None = None,
        from_s: float = Query(0, ge=0, allow_inf_nan=False),
        to_s: float = Query(601, gt=0, allow_inf_nan=False),
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        if from_s >= to_s:
            raise HTTPException(422, "from_s must be less than to_s")
        with connect(settings) as conn:
            required(conn.execute("SELECT id FROM jobs WHERE id=%s", (job_id,)).fetchone())
            rows = conn.execute(
                EVENT_SELECT
                + """ WHERE e.job_id=%s AND e.seq>%s
                AND (%s::text IS NULL OR e.activity=%s) AND (%s::text IS NULL OR e.object_class=%s)
                AND e.start_s<%s AND (e.end_s>%s OR (e.start_s=e.end_s AND e.start_s>=%s))
                ORDER BY e.seq LIMIT %s""",
                (
                    job_id,
                    cursor,
                    activity,
                    activity,
                    object_class,
                    object_class,
                    to_s,
                    from_s,
                    from_s,
                    limit + 1,
                ),
            ).fetchall()
            return page(rows, limit)

    @app.get("/v1/events/{identity}", response_model=EventDetail)
    def event(identity: UUID):
        with connect(settings) as conn:
            row = required(conn.execute(EVENT_SELECT + " WHERE e.id=%s", (identity,)).fetchone())
            row.pop("seq")
            row["reviews"] = conn.execute(
                "SELECT id,verdict,note,created_at FROM reviews WHERE event_id=%s ORDER BY seq",
                (identity,),
            ).fetchall()
            return row

    @app.post("/v1/events/{identity}/reviews", status_code=201, response_model=ReviewRecord)
    def review(identity: UUID, body: ReviewRequest):
        with connect(settings) as conn:
            required(conn.execute("SELECT id FROM events WHERE id=%s", (identity,)).fetchone())
            return conn.execute(
                """INSERT INTO reviews(id,event_id,verdict,note) VALUES(%s,%s,%s,%s)
                                RETURNING id,verdict,note,created_at""",
                (uuid4(), identity, body.verdict, body.note),
            ).fetchone()

    @app.get("/v1/jobs/{identity}/metrics", response_model=Page[MetricSample])
    def metrics(
        identity: UUID, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)
    ):
        with connect(settings) as conn:
            required(conn.execute("SELECT id FROM jobs WHERE id=%s", (identity,)).fetchone())
            return page(
                conn.execute(
                    "SELECT seq,time_s,counts FROM metric_samples WHERE job_id=%s AND seq>%s ORDER BY seq LIMIT %s",
                    (identity, cursor, limit + 1),
                ).fetchall(),
                limit,
            )

    if (ROOT / "web/dist").is_dir():
        app.mount("/", StaticFiles(directory=ROOT / "web/dist", html=True), name="workbench")
    return app


app = create_app()
