BEGIN;

DROP TABLE IF EXISTS podcast_render_jobs;

ALTER TABLE podcast_versions
  DROP COLUMN IF EXISTS render_started_at,
  DROP COLUMN IF EXISTS render_fingerprint,
  DROP COLUMN IF EXISTS render_metadata;

COMMIT;
