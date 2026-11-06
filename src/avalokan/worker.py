"""One supervised worker per database, one bounded child process per clip."""

import json
import signal
import subprocess
import sys
import time

from .db import connect, migrate
from .settings import Settings
from .tracing import configure as configure_tracing
from .tracing import event as trace


def recover(conn):
    # Called only while holding the singleton worker advisory lock. A crashed
    # job retries from the original file. Completion and results are atomic.
    conn.execute("""UPDATE jobs SET status=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,
                 progress=0,error='Worker interrupted; retry limit is three attempts',
                 finished_at=CASE WHEN attempts>=3 THEN now() ELSE NULL END WHERE status='running'""")


def main():
    def stop(signum, frame):
        # subprocess.run kills/waits for its child when interrupted by an
        # exception, so graceful API shutdown cannot leave analysis orphaned.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    settings = Settings()
    migrate(settings)
    with connect(settings, autocommit=True) as lock:
        if not lock.execute("SELECT pg_try_advisory_lock(710201) AS acquired").fetchone()[
            "acquired"
        ]:
            raise SystemExit("Another worker already owns this database")
        recover(lock)
        configure_tracing()
        trace(None, "worker.ready")
        while True:
            row = lock.execute("""UPDATE jobs SET status='running',attempts=attempts+1,error=NULL
                WHERE id=(SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1)
                RETURNING id,attempts""").fetchone()
            if not row:
                time.sleep(0.5)
                continue
            identity = str(row["id"])
            started = time.monotonic()
            trace(identity, "job.start", attempt=row["attempts"])
            try:
                # Same supervised service cgroup: a service restart kills the
                # child too. The parent timeout kills/waits for the child.
                result = subprocess.run(
                    [sys.executable, "-m", "avalokan.engine", identity, str(row["attempts"])],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
                if result.returncode:
                    # Native decoder logs may include file metadata; only emit a
                    # generic failure to API clients. Operator stderr is local.
                    print(result.stderr[-4000:], file=sys.stderr, flush=True)
                    trace(identity, "job.engine_failed", level="error",
                          returncode=result.returncode, stderr_tail=result.stderr[-1500:])
                    raise ValueError(
                        "Analysis failed: invalid timestamps/media, model failure, or resource limit. Check worker logs."
                    )
                try:
                    stats = json.loads(result.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    stats = {}
                trace(identity, "job.completed",
                      attempt=row["attempts"], seconds=round(time.monotonic() - started, 2),
                      analyzed_frames=stats.get("analyzed_frames"),
                      analysis_fps=stats.get("analysis_fps"),
                      events=stats.get("event_count"))
            except (subprocess.TimeoutExpired, ValueError) as exc:
                message = (
                    "Analysis exceeded the 15-minute job limit"
                    if isinstance(exc, subprocess.TimeoutExpired)
                    else str(exc)
                )
                trace(identity, "job.failed", level="error", attempt=row["attempts"],
                      error=message, seconds=round(time.monotonic() - started, 2))
                lock.execute(
                    "UPDATE jobs SET status='failed',error=%s,finished_at=now() WHERE id=%s AND status='running' AND attempts=%s",
                    (message, identity, row["attempts"]),
                )


if __name__ == "__main__":
    main()
