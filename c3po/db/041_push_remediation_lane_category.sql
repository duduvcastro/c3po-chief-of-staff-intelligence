-- Adds the opt-in Web Push category for newly observed automatic remediation PRs.
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
        'remediation_lane_opened',
        'mesa_reading',
        'disk_threshold',
        'security_login',
        'sell_win',
        'hourly_win_rate'
    ]::text[]
);

DO $$
DECLARE
    subscription push_subscriptions%ROWTYPE;
BEGIN
    FOR subscription IN
        SELECT *
        FROM push_subscriptions
        WHERE revoked_at IS NULL
          AND NOT ('remediation_lane_opened' = ANY(categories))
        FOR UPDATE
    LOOP
        UPDATE push_subscriptions
        SET revoked_at = NOW()
        WHERE id = subscription.id;

        INSERT INTO push_subscriptions (
            id,
            user_email,
            endpoint,
            p256dh,
            auth_key,
            categories,
            created_at,
            revoked_at
        ) VALUES (
            gen_random_uuid(),
            subscription.user_email,
            subscription.endpoint,
            subscription.p256dh,
            subscription.auth_key,
            array_append(subscription.categories, 'remediation_lane_opened'),
            NOW(),
            NULL
        );
    END LOOP;
END $$;
