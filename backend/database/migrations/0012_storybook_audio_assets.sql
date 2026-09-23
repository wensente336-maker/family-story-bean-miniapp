BEGIN;

CREATE TABLE storybook_audio_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  storybook_version_id uuid NOT NULL REFERENCES storybook_versions(id) ON DELETE CASCADE,
  page_index smallint NOT NULL CHECK (page_index >= 0),
  kind text NOT NULL CHECK (kind IN ('ORIGINAL_CLIP')),
  source_recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  source_segment_id uuid REFERENCES transcript_segments(id) ON DELETE SET NULL,
  original_start_ms integer NOT NULL CHECK (original_start_ms >= 0),
  original_end_ms integer NOT NULL CHECK (original_end_ms > original_start_ms),
  object_key text NOT NULL,
  media_type text NOT NULL DEFAULT 'audio/mpeg',
  duration_ms integer NOT NULL CHECK (duration_ms > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (storybook_version_id, page_index, kind)
);

CREATE INDEX idx_storybook_audio_assets_version
  ON storybook_audio_assets(storybook_version_id, page_index);

COMMIT;
