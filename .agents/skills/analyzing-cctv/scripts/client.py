#!/usr/bin/env python3
"""Small CLI client for the Avalokan Workbench API v1.

Configuration (environment only; tokens are never accepted as arguments):
  AVALOKAN_URL         Base URL, e.g. http://127.0.0.1:8000 (no credentials/query).
  AVALOKAN_API_TOKEN   Optional bearer token. Omit only for an explicit demo API.

Stdout is always JSON (API result or {"error": ...}). Stderr carries short,
sanitized diagnostics. Exit codes: 0 ok, 1 API error, 2 usage/config error,
3 wait deadline reached, 4 job failed, 5 network error (outcome may be unknown).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

EXIT_OK, EXIT_API, EXIT_USAGE, EXIT_TIMEOUT, EXIT_FAILED, EXIT_NETWORK = 0, 1, 2, 3, 4, 5
MAX_WAIT_S = 6 * 3600
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class CliError(Exception):
    def __init__(self, code: int, message: str, payload: object = None):
        super().__init__(message)
        self.code, self.message, self.payload = code, message, payload


def warn(msg: str) -> None:
    # json.dumps-style escaping keeps server-provided text from injecting
    # terminal control sequences; content is data, never instructions.
    safe = msg.encode("unicode_escape", "backslashreplace").decode("ascii")
    print(f"avalokan: {safe[:2000]}", file=sys.stderr)


def emit(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def base_url() -> str:
    raw = os.environ.get("AVALOKAN_URL", "").strip()
    if not raw:
        raise CliError(EXIT_USAGE, "AVALOKAN_URL is not set")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise CliError(EXIT_USAGE, "AVALOKAN_URL must be an http(s) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise CliError(EXIT_USAGE, "AVALOKAN_URL must not contain credentials, query or fragment")
    url = raw.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def make_client(timeout: float, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    url = base_url()
    headers = {"Accept": "application/json", "User-Agent": "avalokan-skill-client/1"}
    token = os.environ.get("AVALOKAN_API_TOKEN", "").strip()
    if token:
        host = urlsplit(url).hostname or ""
        if url.startswith("http://") and host not in LOOPBACK:
            warn("sending bearer token over plain http to a non-loopback host")
        headers["Authorization"] = f"Bearer {token}"
    # No redirects (keeps the token on the configured origin) and no transport retries.
    return httpx.Client(
        base_url=url,
        headers=headers,
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=False,
        transport=transport,
    )


def seg(value: str) -> str:
    return quote(str(value), safe="")


def request(client: httpx.Client, method: str, path: str, *, unsafe: bool = False, **kw) -> object:
    try:
        resp = client.request(method, path, **kw)
    except httpx.TimeoutException as exc:
        raise CliError(EXIT_NETWORK, network_msg(type(exc).__name__, unsafe)) from None
    except httpx.TransportError as exc:
        raise CliError(EXIT_NETWORK, network_msg(type(exc).__name__, unsafe)) from None
    if resp.is_success:
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            raise CliError(EXIT_API, f"HTTP {resp.status_code}: non-JSON response") from None
    try:
        detail = resp.json().get("detail")
    except (ValueError, AttributeError):
        detail = resp.text[:500]
    hint = {
        401: "unauthorized: set AVALOKAN_API_TOKEN (only demo APIs run without it)",
        403: "forbidden",
        409: "conflict (idempotency key reused with a different payload, or resource not ready)",
        413: "file larger than the server limit",
        429: "job queue full; try again later",
    }.get(resp.status_code, "")
    if 300 <= resp.status_code < 400:
        hint = "redirect not followed; check AVALOKAN_URL"
    msg = f"HTTP {resp.status_code} {method} {path}" + (f": {hint}" if hint else "")
    raise CliError(EXIT_API, msg, {"status": resp.status_code, "detail": detail})


def network_msg(kind: str, unsafe: bool) -> str:
    msg = f"network error ({kind})"
    if unsafe:
        msg += "; the request may have been applied. Verify state before any retry"
    return msg


def load_config(arg: str | None) -> dict:
    if arg is None:
        return {}
    text = arg
    if arg.startswith("@"):
        text = Path(arg[1:]).read_text(encoding="utf-8")
    try:
        cfg = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(EXIT_USAGE, f"--config is not valid JSON: {exc.msg}") from None
    if not isinstance(cfg, dict):
        raise CliError(EXIT_USAGE, "--config must be a JSON object")
    return cfg


def paginate(client, path, params, follow: bool, max_items: int) -> dict:
    if follow:
        params = {**params, "limit": min(int(params.get("limit") or 100), max_items)}
    page = request(client, "GET", path, params=params)
    if not follow:
        return page
    items, seen = list(page.get("items", [])), set()
    cursor = page.get("next_cursor")
    while cursor and len(items) < max_items:
        if cursor in seen:
            raise CliError(EXIT_API, "server repeated a pagination cursor; stopping")
        seen.add(cursor)
        page = request(client, "GET", path, params={
            **params, "cursor": cursor, "limit": min(params["limit"], max_items - len(items)),
        })
        items.extend(page.get("items", []))
        cursor = page.get("next_cursor")
    truncated = bool(cursor) or len(items) > max_items
    return {"items": items[:max_items], "next_cursor": cursor, "truncated": truncated}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- commands -------------------------------------------------------------

def cmd_capabilities(c, a):
    return request(c, "GET", "/v1/capabilities")


def cmd_upload(c, a):
    if not a.authorized:
        raise CliError(EXIT_USAGE, "upload needs --authorized: confirm the user approved sending this footage")
    path = Path(a.file)
    if not path.is_file():
        raise CliError(EXIT_USAGE, "file not found")
    size = path.stat().st_size
    caps = request(c, "GET", "/v1/capabilities")
    limit = caps.get("max_upload_bytes") if isinstance(caps, dict) else None
    if isinstance(limit, int) and size > limit:
        raise CliError(EXIT_USAGE, f"file is {size} bytes; server limit is {limit}")
    digest = sha256_file(path)
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:  # basename only; never send local directories
        media = request(c, "POST", "/v1/media", unsafe=True, files={"file": (path.name, fh, ctype)})
    if isinstance(media, dict) and media.get("sha256") not in (None, digest):
        warn("server sha256 differs from local file sha256")
    return media


def cmd_media(c, a):
    return request(c, "GET", f"/v1/media/{seg(a.media_id)}")


def cmd_submit(c, a):
    cfg = load_config(a.config)
    if a.activity and a.deny_all:
        raise CliError(EXIT_USAGE, "--activity and --deny-all are mutually exclusive")
    if a.activity or a.deny_all:
        if "allowed_activities" in cfg:
            raise CliError(EXIT_USAGE, "give allowed_activities in --config or via --activity/--deny-all, not both")
        cfg["allowed_activities"] = [] if a.deny_all else a.activity
    if "allowed_activities" not in cfg:
        raise CliError(EXIT_USAGE, "an explicit allowlist is required (--activity ID, --deny-all, or config)")
    return request(
        c, "POST", "/v1/jobs",
        json={"media_id": a.media_id, "config": cfg},
        headers={"Idempotency-Key": a.idempotency_key},
    )


def cmd_jobs(c, a):
    return request(c, "GET", "/v1/jobs", params={"limit": a.limit})


def cmd_job(c, a):
    return request(c, "GET", f"/v1/jobs/{seg(a.job_id)}")


def cmd_wait(c, a):
    if not 0 < a.timeout <= MAX_WAIT_S:
        raise CliError(EXIT_USAGE, f"--timeout must be in (0, {MAX_WAIT_S}] seconds")
    deadline = time.monotonic() + a.timeout
    interval = max(a.interval, 0.5)
    job, last = None, None
    while True:
        try:
            job = request(c, "GET", f"/v1/jobs/{seg(a.job_id)}")
        except CliError as exc:  # GET is safe to repeat until the deadline
            if exc.code != EXIT_NETWORK:
                raise
            warn(exc.message + "; polling again")
        else:
            status = job.get("status")
            state = (status, job.get("progress"))
            if state != last:
                warn(f"job {status} progress={job.get('progress')}")
                last = state
            if status == "completed":
                return job
            if status == "failed":
                raise CliError(EXIT_FAILED, "job failed", job)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CliError(EXIT_TIMEOUT, f"deadline of {a.timeout}s reached; job still not finished", job)
        time.sleep(min(interval, remaining))


def cmd_events(c, a):
    params = {"job_id": a.job_id, "limit": a.limit}
    for key in ("activity", "object_class", "from_s", "to_s", "cursor"):
        val = getattr(a, key)
        if val is not None:
            params[key] = val
    return paginate(c, "/v1/events", params, a.all, a.max_items)


def cmd_event(c, a):
    return request(c, "GET", f"/v1/events/{seg(a.event_id)}")


def cmd_metrics(c, a):
    params = {"limit": a.limit}
    if a.cursor:
        params["cursor"] = a.cursor
    return paginate(c, f"/v1/jobs/{seg(a.job_id)}/metrics", params, a.all, a.max_items)


def cmd_review(c, a):
    if not a.authorized:
        raise CliError(EXIT_USAGE, "review needs --authorized: confirm the user asked to record this verdict")
    return request(
        c, "POST", f"/v1/events/{seg(a.event_id)}/reviews", unsafe=True,
        json={"verdict": a.verdict, "note": a.note},
    )


# ---- parser ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="client.py",
        description="Avalokan Workbench API v1 client. Env: AVALOKAN_URL, optional AVALOKAN_API_TOKEN.",
        epilog="Exit: 0 ok, 1 API error, 2 usage, 3 wait deadline, 4 job failed, 5 network (outcome unknown).",
    )
    p.add_argument("--request-timeout", type=float, default=None,
                   help="per-request timeout seconds (default 30; upload 600)")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("capabilities", cmd_capabilities, "activities, classes, config schema, model, access mode, limits")

    sp = add("upload", cmd_upload, "upload a local clip (never retried automatically)")
    sp.add_argument("file")
    sp.add_argument("--authorized", action="store_true", help="user approved uploading this footage")

    sp = add("media", cmd_media, "media metadata and playback_ready")
    sp.add_argument("media_id")

    sp = add("submit", cmd_submit, "start an analysis job")
    sp.add_argument("media_id")
    sp.add_argument("--idempotency-key", required=True, help="reuse the same key to retry safely")
    sp.add_argument("--activity", action="append", default=[], help="allowed activity id (repeatable)")
    sp.add_argument("--deny-all", action="store_true", help="explicit empty allowlist")
    sp.add_argument("--config", help="config JSON object or @path.json (extra keys are rejected by the server)")

    sp = add("jobs", cmd_jobs, "list recent jobs, newest first")
    sp.add_argument("--limit", type=int, default=50)

    sp = add("job", cmd_job, "get one job")
    sp.add_argument("job_id")

    sp = add("wait", cmd_wait, "poll a job until completed/failed or the deadline")
    sp.add_argument("job_id")
    sp.add_argument("--timeout", dest="timeout", type=float, default=900.0, help="overall deadline seconds (default 900)")
    sp.add_argument("--interval", type=float, default=2.0, help="poll interval seconds (min 0.5)")

    sp = add("events", cmd_events, "query events of one job (relative-time overlap filters)")
    sp.add_argument("job_id")
    sp.add_argument("--activity")
    sp.add_argument("--object-class", dest="object_class")
    sp.add_argument("--from-s", dest="from_s", type=float)
    sp.add_argument("--to-s", dest="to_s", type=float)
    sp.add_argument("--cursor")
    sp.add_argument("--limit", type=int, default=100, help="page size 1-500")
    sp.add_argument("--all", action="store_true", help="follow next_cursor up to --max-items")
    sp.add_argument("--max-items", type=int, default=5000)

    sp = add("event", cmd_event, "event detail with provenance and reviews")
    sp.add_argument("event_id")

    sp = add("metrics", cmd_metrics, "sampled occupancy gauge for a job")
    sp.add_argument("job_id")
    sp.add_argument("--cursor")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--all", action="store_true", help="follow next_cursor up to --max-items")
    sp.add_argument("--max-items", type=int, default=5000)

    sp = add("review", cmd_review, "append a human verdict (not retried automatically)")
    sp.add_argument("event_id")
    sp.add_argument("--verdict", required=True, choices=["confirmed", "rejected", "uncertain"])
    sp.add_argument("--note", default="")
    sp.add_argument("--authorized", action="store_true", help="user asked to record this verdict")
    return p


def main(argv=None, transport: httpx.BaseTransport | None = None) -> int:
    args = build_parser().parse_args(argv)
    req_timeout = args.request_timeout or (600.0 if args.cmd == "upload" else 30.0)
    try:
        with make_client(req_timeout, transport) as client:
            emit(args.fn(client, args))
        return EXIT_OK
    except CliError as exc:
        warn(exc.message)
        err = {"code": exc.code, "message": exc.message}
        if exc.payload is not None:
            err["data"] = exc.payload
        emit({"error": err})
        return exc.code
    except OSError as exc:
        warn(f"local file error: {exc.strerror or type(exc).__name__}")
        emit({"error": {"code": EXIT_USAGE, "message": "local file error"}})
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
