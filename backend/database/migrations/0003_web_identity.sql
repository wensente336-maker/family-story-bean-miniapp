BEGIN;

ALTER TABLE users ADD COLUMN phone_hash text;
CREATE UNIQUE INDEX uq_users_phone_hash ON users(phone_hash) WHERE phone_hash IS NOT NULL;

COMMIT;
