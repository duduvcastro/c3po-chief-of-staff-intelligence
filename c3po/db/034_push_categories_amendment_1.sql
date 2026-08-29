-- C3PO_MOBILE_PUSH_V2 Amendment 1: security_login, sell_win, hourly_win_rate.
DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'push_subscriptions'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%categories <@%';
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE push_subscriptions DROP CONSTRAINT %I', constraint_name);
    END IF;
END $$;

ALTER TABLE push_subscriptions
ADD CONSTRAINT push_subscriptions_categories_check CHECK (
    categories <@ ARRAY[
        'kill_criterion',
        'job_failure',
        'governance_critical',
        'mesa_reading',
        'disk_threshold',
        'security_login',
        'sell_win',
        'hourly_win_rate'
    ]::text[]
);
