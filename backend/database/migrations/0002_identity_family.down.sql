BEGIN;

DROP INDEX IF EXISTS idx_users_status;
DROP INDEX IF EXISTS uq_families_owner_user;

COMMIT;
