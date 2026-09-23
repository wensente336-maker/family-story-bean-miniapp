BEGIN;

DROP TABLE IF EXISTS creation_shares;
DROP TABLE IF EXISTS family_privacy_settings;
DROP INDEX IF EXISTS idx_recordings_expiry;

COMMIT;
