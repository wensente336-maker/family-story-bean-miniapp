BEGIN;

CREATE TABLE storybook_experience_tracks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  storybook_version_id uuid NOT NULL REFERENCES storybook_versions(id) ON DELETE CASCADE,
  source_recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'GENERATING'
    CHECK (status IN ('GENERATING', 'READY', 'FAILED')),
  object_key text,
  media_type text NOT NULL DEFAULT 'audio/mpeg',
  duration_ms integer CHECK (duration_ms > 0),
  storyline jsonb NOT NULL,
  cues jsonb NOT NULL DEFAULT '[]'::jsonb,
  render_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_detail text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (storybook_version_id)
);

CREATE INDEX idx_storybook_experience_tracks_family
  ON storybook_experience_tracks(family_id, updated_at DESC);

COMMIT;
