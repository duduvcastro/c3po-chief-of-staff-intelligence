CREATE TABLE IF NOT EXISTS operational_incidents (
    id UUID PRIMARY KEY,
    incident_key TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('attention', 'critical')),
    title TEXT NOT NULL,
    deep_link TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS operational_incident_events (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES operational_incidents(id),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('opened', 'observed', 'reopened', 'acknowledged', 'resolved')
    ),
    actor_email TEXT,
    detail TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_sha256 TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS operational_incident_events_latest_idx
    ON operational_incident_events (incident_id, occurred_at DESC, created_at DESC);

CREATE OR REPLACE FUNCTION reject_operational_incident_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'operational incident events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS operational_incident_events_immutable
    ON operational_incident_events;
CREATE TRIGGER operational_incident_events_immutable
BEFORE UPDATE OR DELETE ON operational_incident_events
FOR EACH ROW EXECUTE FUNCTION reject_operational_incident_event_mutation();
