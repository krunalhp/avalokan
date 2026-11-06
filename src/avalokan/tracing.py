"""Structured trace logging for the Avalokan services.

Every operational event is one JSON line on stdout with a trace id, so a
request, ingest, or analysis job can be followed end to end in the service
logs (`amp orb service logs avalokan`).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from uuid import uuid4

_log = logging.getLogger("avalokan")


def configure(level: int = logging.INFO) -> None:
    if not _log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _log.addHandler(handler)
        _log.setLevel(level)
        _log.propagate = False


def new_trace_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def event(trace_id: str | None, event_name: str, level: str = "info", **fields) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": level,
        "trace_id": trace_id,
        "event": event_name,
        **fields,
    }
    _log.log(
        logging.ERROR if level == "error" else logging.WARNING if level == "warn" else logging.INFO,
        json.dumps(record, default=str),
    )
