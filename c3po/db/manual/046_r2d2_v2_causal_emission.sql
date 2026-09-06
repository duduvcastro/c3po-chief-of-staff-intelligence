-- V2 source emission only. This migration is not run by any application worker.
-- The operational emitter must use a separate non-owner role with SELECT/INSERT
-- only, without UPDATE/DELETE/TRUNCATE/DDL or membership in an owner role.
CREATE TABLE IF NOT EXISTS r2d2_v2_causal_artifacts (
    epoch TEXT NOT NULL CHECK (epoch ~ '^R2D2-V2-(SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}$'),
    session DATE NOT NULL,
    commitment JSONB NOT NULL,
    commitment_sha TEXT NOT NULL CHECK (commitment_sha ~ '^[0-9a-f]{64}$'),
    build_event_id UUID NOT NULL UNIQUE REFERENCES audit_events(id),
    PRIMARY KEY (epoch, session)
);
CREATE TABLE IF NOT EXISTS r2d2_v2_causal_publications (
    build_event_id UUID PRIMARY KEY REFERENCES audit_events(id),
    publication_event_id UUID NOT NULL UNIQUE REFERENCES audit_events(id)
);
-- A separate transaction witnesses that the audit event was already committed.
-- For builds, confirmed_at must precede midnight ET of the entry session.
CREATE TABLE IF NOT EXISTS r2d2_v2_causal_confirmations (
    event_id UUID PRIMARY KEY REFERENCES audit_events(id),
    event_sha TEXT NOT NULL CHECK (event_sha ~ '^[0-9a-f]{64}$'),
    confirmed_at TIMESTAMPTZ NOT NULL
);

CREATE OR REPLACE FUNCTION r2d2_v2_causal_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME <> 'audit_events' THEN
        RAISE EXCEPTION 'V2_CAUSAL_APPEND_ONLY';
    END IF;
    IF OLD.action IN ('r2d2.v2.causal_list_built', 'r2d2.v2.causal_list_published') THEN
        RAISE EXCEPTION 'V2_CAUSAL_APPEND_ONLY';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.action IN ('r2d2.v2.causal_list_built', 'r2d2.v2.causal_list_published') THEN
        RAISE EXCEPTION 'V2_CAUSAL_APPEND_ONLY';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS r2d2_v2_causal_audit_immutable ON audit_events;
CREATE TRIGGER r2d2_v2_causal_audit_immutable BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION r2d2_v2_causal_append_only();
DROP TRIGGER IF EXISTS r2d2_v2_causal_artifacts_immutable ON r2d2_v2_causal_artifacts;
CREATE TRIGGER r2d2_v2_causal_artifacts_immutable BEFORE UPDATE OR DELETE ON r2d2_v2_causal_artifacts
FOR EACH ROW EXECUTE FUNCTION r2d2_v2_causal_append_only();
DROP TRIGGER IF EXISTS r2d2_v2_causal_publications_immutable ON r2d2_v2_causal_publications;
CREATE TRIGGER r2d2_v2_causal_publications_immutable BEFORE UPDATE OR DELETE ON r2d2_v2_causal_publications
FOR EACH ROW EXECUTE FUNCTION r2d2_v2_causal_append_only();
DROP TRIGGER IF EXISTS r2d2_v2_causal_confirmations_immutable ON r2d2_v2_causal_confirmations;
CREATE TRIGGER r2d2_v2_causal_confirmations_immutable BEFORE UPDATE OR DELETE ON r2d2_v2_causal_confirmations
FOR EACH ROW EXECUTE FUNCTION r2d2_v2_causal_append_only();
