CREATE TABLE IF NOT EXISTS schema_version (version integer PRIMARY KEY);
CREATE TABLE IF NOT EXISTS media (
    id uuid PRIMARY KEY, name text NOT NULL, path text NOT NULL, format text NOT NULL,
    duration_s double precision NOT NULL CHECK(duration_s > 0),
    width integer NOT NULL, height integer NOT NULL, codec text NOT NULL,
    size_bytes bigint NOT NULL, sha256 text NOT NULL, playback_path text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY, media_id uuid NOT NULL REFERENCES media(id),
    idempotency_key text NOT NULL UNIQUE, request_hash text NOT NULL,
    config jsonb NOT NULL, status text NOT NULL DEFAULT 'queued'
        CHECK(status IN ('queued','running','completed','failed')),
    progress double precision NOT NULL DEFAULT 0 CHECK(progress >= 0 AND progress <= 1),
    stats jsonb NOT NULL DEFAULT '{}', error text,
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(created_at) WHERE status='queued';
CREATE TABLE IF NOT EXISTS events (
    seq bigserial UNIQUE NOT NULL, id uuid PRIMARY KEY, job_id uuid NOT NULL REFERENCES jobs(id),
    activity text NOT NULL, object_class text NOT NULL, track_id integer NOT NULL,
    start_s double precision NOT NULL CHECK(start_s >= 0),
    end_s double precision NOT NULL CHECK(end_s >= start_s),
    summary text NOT NULL, confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    attributes jsonb NOT NULL, provenance jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_query ON events(job_id, activity, start_s);
CREATE INDEX IF NOT EXISTS events_page ON events(job_id, seq);
CREATE TABLE IF NOT EXISTS metric_samples (
    seq bigserial PRIMARY KEY, job_id uuid NOT NULL REFERENCES jobs(id),
    time_s double precision NOT NULL CHECK(time_s >= 0), counts jsonb NOT NULL,
    UNIQUE(job_id, time_s)
);
CREATE INDEX IF NOT EXISTS metric_page ON metric_samples(job_id,seq);
CREATE TABLE IF NOT EXISTS reviews (
    seq bigserial UNIQUE NOT NULL, id uuid PRIMARY KEY,
    event_id uuid NOT NULL REFERENCES events(id),
    verdict text NOT NULL CHECK(verdict IN ('confirmed','rejected','uncertain')),
    note text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reviews_event ON reviews(event_id,seq DESC);
INSERT INTO schema_version VALUES(1) ON CONFLICT DO NOTHING;
