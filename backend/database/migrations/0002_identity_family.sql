BEGIN;

CREATE UNIQUE INDEX uq_families_owner_user ON families(owner_user_id);
CREATE INDEX idx_users_status ON users(status);

COMMIT;
