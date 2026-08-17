CREATE TABLE IF NOT EXISTS navigation_feed_views (
    user_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    feed_key TEXT NOT NULL CHECK (feed_key IN ('relations', 'intelligence')),
    last_seen_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_email, feed_key)
);

CREATE INDEX IF NOT EXISTS navigation_feed_views_user_time
    ON navigation_feed_views (user_email, last_seen_at DESC);
