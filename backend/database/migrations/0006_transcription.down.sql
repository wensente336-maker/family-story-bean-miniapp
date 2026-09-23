BEGIN;

DROP TABLE IF EXISTS recording_speaker_mappings;

ALTER TABLE transcript_segments
  DROP COLUMN IF EXISTS pipeline_version,
  DROP COLUMN IF EXISTS edited_by_user,
  DROP COLUMN IF EXISTS words,
  DROP COLUMN IF EXISTS original_text;

ALTER TABLE recordings
  DROP COLUMN IF EXISTS transcript_revision,
  DROP COLUMN IF EXISTS asr_model,
  DROP COLUMN IF EXISTS asr_provider,
  DROP COLUMN IF EXISTS transcript_language;

COMMIT;
