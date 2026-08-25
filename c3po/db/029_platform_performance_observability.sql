CREATE TABLE IF NOT EXISTS platform_api_performance_buckets (
    id TEXT PRIMARY KEY CHECK (length(id) = 64),
    process_id UUID NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    bucket_seconds INTEGER NOT NULL CHECK (bucket_seconds BETWEEN 1 AND 3600),
    backend_build_sha TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')),
    route_template TEXT NOT NULL CHECK (route_template LIKE '/api/%' AND position('?' IN route_template) = 0),
    request_count INTEGER NOT NULL CHECK (request_count > 0),
    error_count INTEGER NOT NULL CHECK (error_count BETWEEN 0 AND request_count),
    duration_sum_ms NUMERIC(20, 3) NOT NULL CHECK (duration_sum_ms >= 0),
    duration_max_ms NUMERIC(16, 3) NOT NULL CHECK (duration_max_ms >= 0),
    durations_ms JSONB NOT NULL CHECK (jsonb_typeof(durations_ms) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (process_id, bucket_start, method, route_template)
);

CREATE INDEX IF NOT EXISTS platform_api_performance_buckets_time
    ON platform_api_performance_buckets (bucket_start DESC);

CREATE INDEX IF NOT EXISTS platform_api_performance_buckets_route_build
    ON platform_api_performance_buckets (route_template, backend_build_sha, bucket_start DESC);

CREATE TABLE IF NOT EXISTS platform_page_load_performance_samples (
    sample_id UUID PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL,
    view_key TEXT NOT NULL CHECK (view_key IN (
        'command', 'markets', 'realtime', 'weather', 'portfolio', 'relations',
        'news', 'r2d2', 'candidates', 'matrix', 'chewie', 'onepager',
        'intelligence', 'finance', 'alerts', 'health', 'serverusage', 'leah', 'helm'
    )),
    frontend_build_sha TEXT NOT NULL,
    backend_build_sha TEXT NOT NULL,
    device_class TEXT NOT NULL CHECK (device_class IN ('mobile', 'tablet', 'desktop')),
    total_ms NUMERIC(16, 3) NOT NULL CHECK (total_ms >= 0),
    api_wait_ms NUMERIC(16, 3) NOT NULL CHECK (api_wait_ms >= 0),
    backend_total_ms NUMERIC(16, 3) NOT NULL CHECK (backend_total_ms >= 0),
    render_ms NUMERIC(16, 3) NOT NULL CHECK (render_ms >= 0),
    request_count INTEGER NOT NULL CHECK (request_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS platform_page_load_performance_samples_time
    ON platform_page_load_performance_samples (received_at DESC);

CREATE INDEX IF NOT EXISTS platform_page_load_performance_samples_view_build
    ON platform_page_load_performance_samples (view_key, frontend_build_sha, received_at DESC);
