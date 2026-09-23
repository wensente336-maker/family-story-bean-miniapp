BEGIN;

DROP INDEX IF EXISTS idx_jobs_heartbeat_active;
DROP INDEX IF EXISTS idx_jobs_recording_created;

ALTER TABLE jobs
  DROP COLUMN IF EXISTS execution_token,
  DROP COLUMN IF EXISTS queue_attempted_at,
  DROP COLUMN IF EXISTS dead_lettered_at,
  DROP COLUMN IF EXISTS completed_at,
  DROP COLUMN IF EXISTS started_at,
  DROP COLUMN IF EXISTS heartbeat_at;

COMMIT;
