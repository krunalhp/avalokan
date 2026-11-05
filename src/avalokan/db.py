import psycopg
from psycopg.rows import dict_row

from .settings import ROOT

JOB_SELECT = """SELECT j.id,j.media_id,m.name AS media_name,j.status,j.progress,
    j.config,j.error,j.stats,j.created_at,j.finished_at,
    (SELECT count(*) FROM events e WHERE e.job_id=j.id) AS event_count
    FROM jobs j JOIN media m ON m.id=j.media_id"""
EVENT_SELECT = """SELECT e.*,
    COALESCE((SELECT verdict FROM reviews r WHERE r.event_id=e.id ORDER BY r.seq DESC LIMIT 1),
    'unreviewed') AS review_status FROM events e"""


def connect(settings, **kwargs):
    return psycopg.connect(settings.dsn, row_factory=dict_row, **kwargs)


def migrate(settings):
    with connect(settings) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(710200)")
        conn.execute((ROOT / "migrations/001_workbench.sql").read_text())


if __name__ == "__main__":
    from .settings import Settings

    migrate(Settings())
    print("Database schema ready (version 1)")
