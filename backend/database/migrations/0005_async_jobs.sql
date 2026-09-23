BEGIN;

ALTER TABLE jobs
  ADD COLUMN heartbeat_at timestamptz,
  ADD COLUMN started_at timestamptz,
  ADD COLUMN completed_at timestamptz,
  ADD COLUMN dead_lettered_at timestamptz,
  ADD COLUMN queue_attempted_at timestamptz,
  ADD COLUMN execution_token text;

CREATE INDEX idx_jobs_recording_created ON jobs(recording_id, created_at DESC);
CREATE INDEX idx_jobs_heartbeat_active ON jobs(heartbeat_at)
  WHERE stage IN ('PREPROCESSING', 'TRANSCRIBING', 'ANALYZING', 'GENERATING');

INSERT INTO jobs (
  family_id, recording_id, type, stage, progress, idempotency_key, pipeline_version
)
SELECT
  family_id, id, 'RECORDING_PIPELINE', 'CREATED', 0,
  id::text || ':RECORDING_PIPELINE:storyboard-v1', 'storyboard-v1'
FROM recordings
WHERE status = 'UPLOADED'
ON CONFLICT (idempotency_key) DO NOTHING;

COMMIT;
