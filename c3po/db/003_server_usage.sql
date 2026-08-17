CREATE TABLE IF NOT EXISTS server_usage_samples (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL,
    server_name TEXT NOT NULL,
    region TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    cpu_percent NUMERIC(6, 3),
    disk_total_bytes BIGINT,
    disk_used_bytes BIGINT,
    disk_free_bytes BIGINT,
    source TEXT NOT NULL DEFAULT 'procfs',
    UNIQUE (server_id, collected_at)
);

CREATE INDEX IF NOT EXISTS server_usage_history
    ON server_usage_samples (server_id, collected_at DESC);
