"""URL ingest: fetch a remote video (YouTube and other sites) into media storage.

Runs in a single background thread of the API process. The resulting clip goes
through exactly the same validation and playback preparation as an upload.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from uuid import uuid4

from .db import connect
from .media import probe
from .settings import Settings
from .tracing import event as trace

DOWNLOAD_TIMEOUT_S = 900
FORMAT_COLUMN = "mov"  # yt-dlp merges to MP4, which ffprobe reads as the mov demuxer

_FORMAT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[ext=mp4]/b"


def fetch_title(url: str, trace_id: str, cookies: Path | None = None) -> str:
    command = [
        "yt-dlp", "--no-playlist", "--simulate", "--no-warnings",
        "--print", "%(title).200s", "--", url,
    ]
    if cookies and cookies.is_file():
        command += ["--cookies", str(cookies)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    title = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else ""
    if not title:
        trace(trace_id, "ingest.title.failed", level="warn", returncode=result.returncode)
    return title


def download_media(settings: Settings, ingest_id: str, url: str, trace_id: str) -> None:
    """Run the download and finalize (or fail) the ingest row. Never raises."""
    media_id = uuid4()
    target = settings.data / "media" / f"{media_id}.mp4"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        trace(trace_id, "ingest.download.start", url=url)
        command = [
            "yt-dlp", "--no-playlist", "--no-warnings",
            "-f", _FORMAT,
            "--merge-output-format", "mp4",
            "--no-part",
            "-o", str(target),
            "--", url,
        ]
        cookies = settings.cookies_file
        if cookies.is_file():
            command += ["--cookies", str(cookies)]
            trace(trace_id, "ingest.using_cookies")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT_S,
        )
        if result.returncode or not target.is_file():
            detail = (result.stderr or result.stdout or "download produced no file").strip().splitlines()
            message = detail[-1][:300] if detail else "download produced no file"
            if "Sign in to confirm" in (result.stderr or "") or "Sign in to confirm" in message:
                message = (
                    "The video host requires sign-in from this server's IP. Export your "
                    "browser cookies (cookies.txt) and save it to "
                    ".data/secrets/youtube-cookies.txt, then retry."
                )
            raise ValueError(message)
        trace(trace_id, "ingest.download.done", size_bytes=target.stat().st_size)

        title = fetch_title(url, trace_id, cookies)
        metadata = probe(target, FORMAT_COLUMN, settings.max_duration)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        with connect(settings) as conn:
            conn.execute(
                """INSERT INTO media(id,name,path,format,duration_s,width,height,codec,size_bytes,sha256)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    media_id,
                    title or url[:200],
                    str(target.resolve()),
                    FORMAT_COLUMN,
                    metadata["duration_s"],
                    metadata["width"],
                    metadata["height"],
                    metadata["codec"],
                    target.stat().st_size,
                    digest,
                ),
            )
            conn.execute(
                "UPDATE media_ingests SET status='ready',media_id=%s,error=NULL WHERE id=%s",
                (media_id, ingest_id),
            )
        trace(trace_id, "ingest.ready", media_id=str(media_id), **metadata)
    except Exception as exc:
        message = str(exc).replace(str(settings.data), "…")
        target.unlink(missing_ok=True)
        with connect(settings) as conn:
            conn.execute(
                "UPDATE media_ingests SET status='failed',error=%s WHERE id=%s AND status='downloading'",
                (message[:500], ingest_id),
            )
        trace(trace_id, "ingest.failed", level="error", error=message[:500])
