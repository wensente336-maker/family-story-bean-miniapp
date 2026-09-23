BEGIN;

ALTER TABLE recordings
  ADD COLUMN source_type text NOT NULL DEFAULT 'audio_upload'
    CHECK (source_type IN ('audio_upload', 'video_upload', 'mobile_recording', 'recording_bean'));

COMMIT;
