CREATE TABLE IF NOT EXISTS media_ingests (
    id uuid PRIMARY KEY,
    url text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'downloading'
        CHECK(status IN ('downloading','ready','failed')),
    error text,
    media_id uuid REFERENCES media(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS media_ingests_page ON media_ingests(created_at DESC);
INSERT INTO schema_version VALUES(2) ON CONFLICT DO NOTHING;
