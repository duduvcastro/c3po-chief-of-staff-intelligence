ALTER TABLE access_users
    ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '["read"]'::jsonb;

UPDATE access_users
SET capabilities = '["read", "onepager_generate", "delete"]'::jsonb
WHERE role = 'owner';

UPDATE access_users
SET capabilities = '["read"]'::jsonb
WHERE role = 'member' AND (capabilities IS NULL OR jsonb_typeof(capabilities) <> 'array');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'access_users_capabilities_array'
    ) THEN
        ALTER TABLE access_users
            ADD CONSTRAINT access_users_capabilities_array
            CHECK (jsonb_typeof(capabilities) = 'array');
    END IF;
END $$;
