BEGIN;

ALTER TABLE recordings
  ADD COLUMN transcript_language text,
  ADD COLUMN asr_provider text,
  ADD COLUMN asr_model text,
  ADD COLUMN transcript_revision integer NOT NULL DEFAULT 0;

ALTER TABLE transcript_segments
  ADD COLUMN original_text text,
  ADD COLUMN words jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN edited_by_user boolean NOT NULL DEFAULT false,
  ADD COLUMN pipeline_version text NOT NULL DEFAULT 'storyboard-v1';

UPDATE transcript_segments SET original_text = text WHERE original_text IS NULL;
ALTER TABLE transcript_segments ALTER COLUMN original_text SET NOT NULL;

CREATE TABLE recording_speaker_mappings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  speaker_key text NOT NULL,
  family_member_id uuid REFERENCES family_members(id) ON DELETE SET NULL,
  display_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (recording_id, speaker_key)
);

CREATE INDEX idx_speaker_mappings_recording
  ON recording_speaker_mappings(recording_id, speaker_key);

COMMIT;
