BEGIN;

ALTER TABLE recordings
  DROP COLUMN IF EXISTS error_code,
  DROP COLUMN IF EXISTS original_file_name,
  DROP COLUMN IF EXISTS file_size;

COMMIT;
