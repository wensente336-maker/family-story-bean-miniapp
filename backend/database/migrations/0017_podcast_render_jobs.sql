BEGIN;

ALTER TABLE podcast_versions
  ADD COLUMN render_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN render_fingerprint text,
  ADD COLUMN render_started_at timestamptz;

CREATE TABLE podcast_render_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'CREATED'
    CHECK (status IN ('CREATED', 'GENERATING', 'COMPLETED', 'FAILED')),
  progress smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  retry_count smallint NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  idempotency_key text NOT NULL UNIQUE,
  execution_token text,
  heartbeat_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  error_code text,
  error_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (podcast_version_id)
);

CREATE INDEX idx_podcast_render_jobs_status
  ON podcast_render_jobs(status, updated_at DESC);

COMMIT;
