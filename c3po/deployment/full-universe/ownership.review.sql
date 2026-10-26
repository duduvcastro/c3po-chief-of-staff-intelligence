-- DORMANT REVIEW ARTIFACT. Not in db/*.sql; never applied by Database.initialize.
-- No role, credential, epoch, served generation or schedule is created here.
-- Installation and first epoch require separate verified PostgreSQL/role facts,
-- Fable review and an ordered PIT-free operational procedure. Do not run ad hoc.
BEGIN;

DO $prerequisites$
DECLARE role_name text; role_row record; relation_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['c3po', 'c3po_full_universe_owner',
      'c3po_full_universe_publisher', 'c3po_full_universe_operator'] LOOP
    SELECT * INTO role_row FROM pg_catalog.pg_roles WHERE rolname = role_name;
    IF NOT FOUND OR role_row.rolsuper OR role_row.rolcreaterole OR role_row.rolcreatedb OR role_row.rolbypassrls THEN
      RAISE EXCEPTION 'reviewed nonprivileged role prerequisite absent/unsafe: %', role_name;
    END IF;
    IF role_name = 'c3po_full_universe_owner' AND role_row.rolcanlogin THEN
      RAISE EXCEPTION 'storage owner must be NOLOGIN';
    END IF;
    IF role_name IN ('c3po_full_universe_publisher', 'c3po_full_universe_operator') AND NOT role_row.rolcanlogin THEN
      RAISE EXCEPTION 'publisher/operator need distinct authenticated principals, not caller SET ROLE: %', role_name;
    END IF;
  END LOOP;
  IF pg_catalog.pg_has_role('c3po', 'c3po_full_universe_owner', 'MEMBER')
     OR pg_catalog.pg_has_role('c3po', 'c3po_full_universe_publisher', 'MEMBER')
     OR pg_catalog.pg_has_role('c3po', 'c3po_full_universe_operator', 'MEMBER')
     OR pg_catalog.pg_has_role('c3po_full_universe_publisher', 'c3po_full_universe_owner', 'MEMBER')
     OR pg_catalog.pg_has_role('c3po_full_universe_operator', 'c3po_full_universe_owner', 'MEMBER') THEN
    RAISE EXCEPTION 'application/publisher/operator must not inherit or assume privileged publication roles';
  END IF;
  FOREACH relation_name IN ARRAY ARRAY['analysis_snapshots', 'valuation_predictions', 'valuation_official_selection'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname='public' AND c.relname=relation_name
                     AND c.relowner=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='c3po_full_universe_owner')) THEN
      RAISE EXCEPTION 'canonical table must already have the reviewed isolated owner: %', relation_name;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' AND c.relname=relation_name
                 AND (c.relowner IN (SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN
                   ('c3po', 'c3po_full_universe_publisher', 'c3po_full_universe_operator'))
                   OR pg_catalog.pg_has_role('c3po', c.relowner, 'MEMBER')
                   OR pg_catalog.pg_has_role('c3po_full_universe_publisher', c.relowner, 'MEMBER')
                   OR pg_catalog.pg_has_role('c3po_full_universe_operator', c.relowner, 'MEMBER'))) THEN
      RAISE EXCEPTION 'canonical table ownership permits trigger bypass: %', relation_name;
    END IF;
  END LOOP;
END
$prerequisites$;

CREATE SCHEMA c3po_full_universe AUTHORIZATION c3po_full_universe_owner;
REVOKE ALL ON SCHEMA c3po_full_universe FROM PUBLIC;
GRANT USAGE ON SCHEMA c3po_full_universe TO c3po, c3po_full_universe_publisher, c3po_full_universe_operator;

-- Empty on installation. Only the NOLOGIN owner may append a genuinely reviewed
-- readiness epoch later, under the same canonical table lock protocol. There is
-- NO enable API. Installing this DDL itself fences old writers; it must not be
-- installed until migration/IR/targeted/operator compatibility is reviewed.
-- Missing/expired readiness never restores legacy writers. Append-only epochs.
CREATE TABLE c3po_full_universe.epochs (
  sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  epoch_id uuid NOT NULL UNIQUE,
  source text NOT NULL CHECK (source IN ('official_blend_v1','official_internal_v1')),
  source_version text NOT NULL,
  code_pins_sha256 text NOT NULL CHECK (code_pins_sha256 ~ '^[0-9a-f]{64}$'),
  readiness_receipt_sha256 text NOT NULL CHECK (readiness_receipt_sha256 ~ '^[0-9a-f]{64}$'),
  reviewed_at timestamptz NOT NULL,
  readiness_valid_until timestamptz NOT NULL CHECK (readiness_valid_until > reviewed_at)
);
ALTER TABLE c3po_full_universe.epochs OWNER TO c3po_full_universe_owner;
REVOKE ALL ON c3po_full_universe.epochs FROM PUBLIC, c3po, c3po_full_universe_publisher, c3po_full_universe_operator;
GRANT SELECT ON c3po_full_universe.epochs TO c3po_full_universe_publisher, c3po_full_universe_operator;

CREATE TABLE c3po_full_universe.cohorts (
  transaction_id uuid PRIMARY KEY,
  epoch_id uuid NOT NULL REFERENCES c3po_full_universe.epochs(epoch_id),
  expected_predecessor uuid NOT NULL REFERENCES public.valuation_official_selection(generation_id),
  cycles jsonb NOT NULL,
  stages jsonb NOT NULL,
  catalogues jsonb NOT NULL,
  preparation_sha256 text NOT NULL CHECK (preparation_sha256 ~ '^[0-9a-f]{64}$'),
  backend_pid integer NOT NULL DEFAULT pg_catalog.pg_backend_pid(),
  transaction_number bigint NOT NULL DEFAULT pg_catalog.txid_current(),
  authenticated_principal name NOT NULL DEFAULT session_user,
  CHECK (jsonb_typeof(cycles)='object' AND jsonb_typeof(stages)='object' AND jsonb_typeof(catalogues)='object')
);
ALTER TABLE c3po_full_universe.cohorts OWNER TO c3po_full_universe_owner;
REVOKE ALL ON c3po_full_universe.cohorts FROM PUBLIC, c3po, c3po_full_universe_publisher, c3po_full_universe_operator;
GRANT SELECT, INSERT ON c3po_full_universe.cohorts TO c3po_full_universe_publisher;

CREATE FUNCTION c3po_full_universe.enforced() RETURNS boolean
LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, c3po_full_universe
AS $$ SELECT true $$;
-- A constant installed fence cannot disappear under an old MVCC epoch snapshot.
ALTER FUNCTION c3po_full_universe.enforced() OWNER TO c3po_full_universe_owner;
REVOKE ALL ON FUNCTION c3po_full_universe.enforced() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION c3po_full_universe.enforced() TO c3po, c3po_full_universe_publisher, c3po_full_universe_operator;

-- Lock rights stay with the isolated table owner; the publisher is never given
-- UPDATE/DELETE/TRUNCATE just to acquire a table lock. No ownership assertion is
-- taken from a GUC, JSON flag or activated_by string.
CREATE FUNCTION c3po_full_universe.lock_cohort() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, c3po_full_universe
AS $$ BEGIN
  IF session_user <> 'c3po_full_universe_publisher' THEN
    RAISE EXCEPTION USING ERRCODE='PZ001', MESSAGE='dedicated_publisher_principal_required';
  END IF;
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION USING ERRCODE='PZ003', MESSAGE='read_committed_required_for_readiness_revalidation';
  END IF;
  LOCK TABLE public.analysis_snapshots, public.valuation_predictions, public.valuation_official_selection,
    c3po_full_universe.epochs IN SHARE ROW EXCLUSIVE MODE NOWAIT;
END $$;
ALTER FUNCTION c3po_full_universe.lock_cohort() OWNER TO c3po_full_universe_owner;
REVOKE ALL ON FUNCTION c3po_full_universe.lock_cohort() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION c3po_full_universe.lock_cohort() TO c3po_full_universe_publisher;

CREATE FUNCTION c3po_full_universe.append_only() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, c3po_full_universe
AS $$ BEGIN RAISE EXCEPTION USING ERRCODE='PZ006', MESSAGE='full_universe_history_is_append_only'; END $$;
ALTER FUNCTION c3po_full_universe.append_only() OWNER TO c3po_full_universe_owner;
CREATE TRIGGER epochs_append_only BEFORE UPDATE OR DELETE ON c3po_full_universe.epochs
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.append_only();
CREATE TRIGGER cohorts_append_only BEFORE UPDATE OR DELETE ON c3po_full_universe.cohorts
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.append_only();

CREATE FUNCTION c3po_full_universe.bind_cohort() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, c3po_full_universe
AS $$
DECLARE epoch c3po_full_universe.epochs%ROWTYPE; market_key text;
BEGIN
  IF session_user <> 'c3po_full_universe_publisher' OR current_user <> session_user THEN
    RAISE EXCEPTION USING ERRCODE='PZ001', MESSAGE='dedicated_publisher_principal_required';
  END IF;
  PERFORM c3po_full_universe.lock_cohort();
  SELECT * INTO epoch FROM c3po_full_universe.epochs ORDER BY sequence DESC LIMIT 1;
  IF NOT FOUND OR epoch.epoch_id <> NEW.epoch_id OR epoch.reviewed_at > clock_timestamp()
      OR epoch.readiness_valid_until <= clock_timestamp() THEN
    RAISE EXCEPTION USING ERRCODE='PZ002', MESSAGE='publication_readiness_epoch_absent_or_expired';
  END IF;
  IF NOT (NEW.cycles ?& ARRAY['B3','NASDAQ','NYSE']) OR (SELECT count(*) FROM jsonb_object_keys(NEW.cycles)) <> 3
      OR NOT (NEW.stages ?& ARRAY['B3','NASDAQ','NYSE']) OR (SELECT count(*) FROM jsonb_object_keys(NEW.stages)) <> 3
      OR NOT (NEW.catalogues ?& ARRAY['B3','NASDAQ','NYSE']) OR (SELECT count(*) FROM jsonb_object_keys(NEW.catalogues)) <> 3 THEN
    RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='complete_three_market_cohort_required';
  END IF;
  FOREACH market_key IN ARRAY ARRAY['B3','NASDAQ','NYSE'] LOOP
    IF NOT EXISTS (SELECT 1 FROM public.analysis_snapshots s WHERE s.id=(NEW.stages->>market_key)::uuid
                   AND s.analysis_type='full_universe_stage' AND s.entity_key=market_key
                   AND s.inputs->>'source_manifest_sha256'=NEW.catalogues->>market_key
                   AND s.inputs->>'canonical_methodology_version'=epoch.source_version) THEN
      RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='cohort_stage_fk_or_catalogue_mismatch';
    END IF;
  END LOOP;
  NEW.backend_pid := pg_backend_pid();
  NEW.transaction_number := txid_current();
  NEW.authenticated_principal := session_user;
  RETURN NEW;
END $$;
ALTER FUNCTION c3po_full_universe.bind_cohort() OWNER TO c3po_full_universe_owner;
CREATE TRIGGER bind_cohort BEFORE INSERT ON c3po_full_universe.cohorts
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.bind_cohort();

-- SECURITY INVOKER is essential: a SECURITY DEFINER trigger owned by the storage
-- owner would erase the very current_user boundary it is meant to enforce.
CREATE FUNCTION c3po_full_universe.fence_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, c3po_full_universe
AS $$
DECLARE kind text; market_key text; cycle_key uuid; cohort c3po_full_universe.cohorts%ROWTYPE;
        stage public.analysis_snapshots%ROWTYPE; original public.valuation_predictions%ROWTYPE;
        head public.valuation_official_selection%ROWTYPE; epoch c3po_full_universe.epochs%ROWTYPE;
        authority timestamptz; freeze_until timestamptz;
BEGIN
  IF TG_TABLE_NAME='analysis_snapshots' THEN
    kind := NEW.analysis_type;
    cycle_key := NEW.id;
  ELSIF TG_TABLE_NAME='valuation_predictions' THEN
    cycle_key := NEW.cycle_id;
    SELECT analysis_type INTO kind FROM public.analysis_snapshots WHERE id=NEW.cycle_id;
  ELSE kind := 'selection'; END IF;
  -- Existing studies/PIT/stage/OnePager namespaces are not fenced by this work.
  IF kind IS NULL OR kind NOT IN ('selection','valuation_universe','security_valuation') THEN
    IF session_user='c3po_full_universe_publisher' THEN
      RAISE EXCEPTION USING ERRCODE='PZ005', MESSAGE='publisher_principal_cannot_write_study_or_stage_namespaces';
    END IF;
    RETURN NEW;
  END IF;
  -- The artifact is dormant only because it is uninstalled/outside migrations.
  -- Once installed it ALWAYS fences legacy writers, even with no visible epoch.
  IF session_user='c3po_full_universe_operator' AND kind='selection' THEN
    -- Principal isolation is necessary but not an accepted mesa order. No
    -- source-switch/freeze/rollback adapter is implemented by this artifact.
    RAISE EXCEPTION USING ERRCODE='PZ005', MESSAGE='verified_operator_order_adapter_not_implemented';
  END IF;
  IF session_user <> 'c3po_full_universe_publisher' OR current_user <> session_user THEN
    RAISE EXCEPTION USING ERRCODE='PZ001', MESSAGE='legacy_canonical_writer_fenced';
  END IF;
  IF kind='security_valuation' THEN
    RAISE EXCEPTION USING ERRCODE='PZ005', MESSAGE='targeted_publication_adapter_not_implemented';
  END IF;
  SELECT * INTO epoch FROM c3po_full_universe.epochs ORDER BY sequence DESC LIMIT 1;
  IF epoch.reviewed_at > clock_timestamp() OR epoch.readiness_valid_until <= clock_timestamp() THEN
    RAISE EXCEPTION USING ERRCODE='PZ002', MESSAGE='publication_readiness_epoch_expired_fence_remains';
  END IF;
  IF kind='selection' THEN
    SELECT * INTO cohort FROM c3po_full_universe.cohorts c WHERE c.cycles=NEW.cycles
      AND c.epoch_id=epoch.epoch_id AND c.backend_pid=pg_backend_pid()
      AND c.transaction_number=txid_current() AND c.authenticated_principal=session_user;
  ELSE
    SELECT * INTO cohort FROM c3po_full_universe.cohorts c WHERE c.epoch_id=epoch.epoch_id
      AND c.backend_pid=pg_backend_pid() AND c.transaction_number=txid_current()
      AND c.authenticated_principal=session_user AND EXISTS
        (SELECT 1 FROM jsonb_each_text(c.cycles) p WHERE p.value=cycle_key::text);
  END IF;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='same_transaction_cohort_registration_required'; END IF;
  IF TG_TABLE_NAME='analysis_snapshots' THEN
    market_key := replace(NEW.entity_key,'_UNIVERSE','');
    SELECT * INTO stage FROM public.analysis_snapshots WHERE id=(cohort.stages->>market_key)::uuid;
    IF NOT FOUND OR market_key NOT IN ('B3','NASDAQ','NYSE') OR NEW.id::text IS DISTINCT FROM cohort.cycles->>market_key OR kind <> 'valuation_universe'
        OR NEW.inputs->>'methodology_version' IS DISTINCT FROM epoch.source_version
        OR NEW.inputs->>'rerun_of' IS DISTINCT FROM stage.id::text
        OR NEW.inputs->>'source_manifest_sha256' IS DISTINCT FROM cohort.catalogues->>market_key
        OR NEW.published_at < stage.published_at
        OR (NEW.inputs->>'prediction_instant')::timestamptz IS DISTINCT FROM
           (SELECT min(p.prediction_instant) FROM public.valuation_predictions p WHERE p.cycle_id=stage.id)
        OR NEW.outputs->'rows' IS DISTINCT FROM stage.outputs->'rows'
        OR NEW.outputs->'not_evaluable' IS DISTINCT FROM stage.outputs->'not_evaluable'
        OR NEW.outputs->'inventory_count' IS DISTINCT FROM stage.outputs->'inventory_count'
        OR NEW.outputs->'universe_size' IS DISTINCT FROM stage.outputs->'inventory_count' THEN
      RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='official_cycle_does_not_preserve_registered_stage';
    END IF;
  ELSIF TG_TABLE_NAME='valuation_predictions' THEN
    market_key := NEW.market;
    IF market_key IS NULL OR market_key NOT IN ('B3','NASDAQ','NYSE') OR NEW.cycle_id IS NULL
        OR NEW.cycle_id::text IS DISTINCT FROM cohort.cycles->>market_key
        OR NOT EXISTS (SELECT 1 FROM public.analysis_snapshots s WHERE s.id=NEW.cycle_id
                        AND s.analysis_type='valuation_universe' AND s.entity_key=market_key||'_UNIVERSE') THEN
      RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='prediction_market_cycle_binding_required';
    END IF;
    SELECT * INTO stage FROM public.analysis_snapshots s WHERE s.id=(cohort.stages->>market_key)::uuid;
    IF NOT FOUND OR stage.analysis_type IS DISTINCT FROM 'full_universe_stage'
        OR stage.entity_key IS DISTINCT FROM market_key
        OR stage.inputs->>'source_manifest_sha256' IS DISTINCT FROM cohort.catalogues->>market_key THEN
      RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='prediction_market_stage_binding_required';
    END IF;
    SELECT * INTO original FROM public.valuation_predictions p WHERE p.cycle_id=stage.id
      AND p.source=NEW.source AND p.market=market_key AND p.symbol=NEW.symbol;
    IF NOT FOUND OR NEW.source NOT IN ('official_blend_v1','official_internal_v1') OR NEW.scope <> 'universe'
        OR ROW(NEW.source_version,NEW.session_date,NEW.prediction_instant,NEW.tp,NEW.buy_in,NEW.internal_tp,
          NEW.consensus_tp,NEW.consensus_source,NEW.analyst_count,NEW.consensus_weight_percent,NEW.price,NEW.currency)
           IS DISTINCT FROM ROW(original.source_version,original.session_date,original.prediction_instant,original.tp,original.buy_in,original.internal_tp,
          original.consensus_tp,original.consensus_source,original.analyst_count,original.consensus_weight_percent,original.price,original.currency)
        OR NEW.decomposition-'provenance' IS DISTINCT FROM original.decomposition-'provenance'
        OR (NEW.decomposition->'provenance')-ARRAY['rerun_of','stage_record_sha256'] IS DISTINCT FROM (original.decomposition->'provenance')-'rerun_of'
        OR NEW.decomposition->'provenance'->>'rerun_of' IS DISTINCT FROM original.cycle_id::text
        OR NEW.decomposition->'provenance'->>'stage_record_sha256' IS DISTINCT FROM original.row_sha256
        OR NEW.published_at IS DISTINCT FROM (SELECT s.published_at FROM public.analysis_snapshots s WHERE s.id=NEW.cycle_id) THEN
      RAISE EXCEPTION USING ERRCODE='PZ004', MESSAGE='official_prediction_does_not_preserve_canonical_stage_record';
    END IF;
  ELSE
    SELECT * INTO head FROM public.valuation_official_selection ORDER BY activated_at DESC,created_at DESC LIMIT 1;
    IF NEW.previous_generation_id IS DISTINCT FROM head.generation_id OR NEW.previous_generation_id <> cohort.expected_predecessor
        OR NEW.source <> head.source OR NEW.source_version <> head.source_version OR NEW.source <> epoch.source
        OR NEW.source_version <> epoch.source_version OR NOT NEW.validated_complete
        OR NEW.receipt @> '{"explicit":true}'::jsonb OR NEW.activated_at <= head.activated_at THEN
      RAISE EXCEPTION USING ERRCODE='PZ003', MESSAGE='same_source_version_expected_predecessor_required';
    END IF;
    IF head.receipt @> '{"explicit":true}'::jsonb AND jsonb_typeof(head.receipt->'freeze')='object' THEN
      BEGIN freeze_until := LEAST((head.receipt->'freeze'->>'until')::timestamptz,head.activated_at+interval '16 hours');
      EXCEPTION WHEN OTHERS THEN freeze_until := head.activated_at+interval '16 hours'; END;
      IF clock_timestamp() < COALESCE(freeze_until,head.activated_at+interval '16 hours') THEN
        RAISE EXCEPTION USING ERRCODE='PZ003', MESSAGE='existing_mesa_freeze_holds_publication';
      END IF;
    END IF;
    SELECT activated_at INTO authority FROM public.valuation_official_selection WHERE receipt @> '{"explicit":true}'::jsonb
      ORDER BY activated_at DESC,created_at DESC LIMIT 1;
    FOREACH market_key IN ARRAY ARRAY['B3','NASDAQ','NYSE'] LOOP
      IF NOT EXISTS (SELECT 1 FROM public.analysis_snapshots s WHERE s.id=(NEW.cycles->>market_key)::uuid
                     AND s.analysis_type='valuation_universe' AND s.entity_key=market_key||'_UNIVERSE')
          OR EXISTS (SELECT 1 FROM public.valuation_predictions p WHERE p.cycle_id=(NEW.cycles->>market_key)::uuid
                      AND p.market IS DISTINCT FROM market_key)
          OR (SELECT count(*) FROM public.valuation_predictions p WHERE p.cycle_id=(NEW.cycles->>market_key)::uuid
               AND p.market=market_key AND p.scope='universe' AND p.source_version=epoch.source_version
               AND p.source IN ('official_blend_v1','official_internal_v1')) IS DISTINCT FROM
             (SELECT 2*jsonb_array_length(s.outputs->'rows') FROM public.analysis_snapshots s WHERE s.id=(NEW.cycles->>market_key)::uuid)
          OR EXISTS (SELECT 1 FROM public.analysis_snapshots s, jsonb_array_elements(s.outputs->'rows') listing_row,
                       unnest(ARRAY['official_blend_v1','official_internal_v1']) source_name
                     WHERE s.id=(NEW.cycles->>market_key)::uuid AND NOT EXISTS
                       (SELECT 1 FROM public.valuation_predictions p WHERE p.cycle_id=s.id AND p.source=source_name
                          AND p.symbol=listing_row->>'symbol' AND p.market=market_key AND p.source_version=epoch.source_version))
          OR (authority IS NOT NULL AND EXISTS (SELECT 1 FROM public.valuation_predictions p
               WHERE p.cycle_id=(NEW.cycles->>market_key)::uuid AND p.prediction_instant<=authority)) THEN
        RAISE EXCEPTION USING ERRCODE='PZ003', MESSAGE='canonical_records_or_explicit_order_gate_failed';
      END IF;
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION c3po_full_universe.fence_insert() OWNER TO c3po_full_universe_owner;
CREATE TRIGGER full_universe_snapshot_fence BEFORE INSERT ON public.analysis_snapshots
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.fence_insert();
CREATE TRIGGER full_universe_prediction_fence BEFORE INSERT ON public.valuation_predictions
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.fence_insert();
CREATE TRIGGER full_universe_selection_fence BEFORE INSERT ON public.valuation_official_selection
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.fence_insert();

-- The existing official record/selection tables are already append-only. The
-- snapshot table is not: fence canonical row edits too, without fencing updates
-- in unrelated study/PIT namespaces. Changing a namespace cannot escape it.
CREATE FUNCTION c3po_full_universe.canonical_snapshot_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, c3po_full_universe
AS $$
DECLARE canonical boolean;
BEGIN
  canonical := OLD.analysis_type IN ('valuation_universe','security_valuation');
  IF TG_OP='UPDATE' THEN
    canonical := canonical OR NEW.analysis_type IN ('valuation_universe','security_valuation');
  END IF;
  IF canonical AND c3po_full_universe.enforced() THEN
    RAISE EXCEPTION USING ERRCODE='PZ006', MESSAGE='owned_canonical_snapshot_is_immutable';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION c3po_full_universe.canonical_snapshot_immutable() OWNER TO c3po_full_universe_owner;
CREATE TRIGGER full_universe_snapshot_immutable BEFORE UPDATE OR DELETE ON public.analysis_snapshots
FOR EACH ROW EXECUTE FUNCTION c3po_full_universe.canonical_snapshot_immutable();

GRANT SELECT, INSERT ON public.analysis_snapshots, public.valuation_predictions, public.valuation_official_selection TO c3po_full_universe_publisher;
GRANT SELECT ON public.analysis_snapshots, public.valuation_predictions, public.valuation_official_selection TO c3po_full_universe_operator;
GRANT INSERT ON public.valuation_official_selection TO c3po_full_universe_operator;
-- The trigger still denies that role. This grant is not an operator-order API;
-- readiness must not be enabled before a genuine guarded operator route exists.
-- Deliberately no epoch rows, role passwords/memberships, role/table ownership
-- changes, enablement function, trigger bypass, PIT migration or schedule here.
COMMIT;
