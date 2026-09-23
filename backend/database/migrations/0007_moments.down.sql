BEGIN;

DROP TABLE IF EXISTS moment_feedback;
DROP INDEX IF EXISTS idx_moments_recording_rank_version;
ALTER TABLE moments
  DROP CONSTRAINT IF EXISTS moments_selection_state,
  DROP CONSTRAINT IF EXISTS moments_time_bounds,
  DROP COLUMN IF EXISTS edited_by_user,
  DROP COLUMN IF EXISTS transcript_revision,
  DROP COLUMN IF EXISTS score_breakdown,
  DROP COLUMN IF EXISTS selection_state,
  DROP COLUMN IF EXISTS end_ms,
  DROP COLUMN IF EXISTS start_ms,
  DROP COLUMN IF EXISTS rank;

COMMIT;
