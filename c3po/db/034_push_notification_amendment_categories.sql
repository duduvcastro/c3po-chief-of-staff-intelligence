DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'push_subscriptions'::regclass
          AND conname = 'push_subscriptions_categories_check'
          AND pg_get_constraintdef(oid) LIKE '%security_login%'
          AND pg_get_constraintdef(oid) LIKE '%sell_win%'
          AND pg_get_constraintdef(oid) LIKE '%hourly_win_rate%'
    ) THEN
        ALTER TABLE push_subscriptions
            DROP CONSTRAINT IF EXISTS push_subscriptions_categories_check;
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
                ]::TEXT[]
            );
    END IF;
END
$$;
