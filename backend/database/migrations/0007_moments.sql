BEGIN;

ALTER TABLE moments
  ADD COLUMN rank smallint,
  ADD COLUMN start_ms integer,
  ADD COLUMN end_ms integer,
  ADD COLUMN selection_state text NOT NULL DEFAULT 'candidate',
  ADD COLUMN score_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN transcript_revision integer NOT NULL DEFAULT 0,
  ADD COLUMN edited_by_user boolean NOT NULL DEFAULT false;

ALTER TABLE moments
  ADD CONSTRAINT moments_time_bounds CHECK (
    start_ms IS NULL OR (start_ms >= 0 AND end_ms > start_ms)
  ),
  ADD CONSTRAINT moments_selection_state CHECK (
    selection_state IN ('candidate', 'kept', 'dismissed')
  );

CREATE UNIQUE INDEX idx_moments_recording_rank_version
  ON moments(recording_id, rank, pipeline_version) WHERE rank IS NOT NULL;

CREATE TABLE moment_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  moment_id uuid NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
  action text NOT NULL CHECK (action IN ('kept', 'dismissed', 'boundary_changed')),
  previous_value jsonb NOT NULL DEFAULT '{}'::jsonb,
  new_value jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_moment_feedback_recording ON moment_feedback(recording_id, created_at);

COMMIT;
