BEGIN;

ALTER TABLE recordings
  ADD COLUMN file_size bigint CHECK (file_size IS NULL OR file_size > 0),
  ADD COLUMN original_file_name text,
  ADD COLUMN error_code text;

UPDATE recordings SET original_file_name = title WHERE original_file_name IS NULL;
ALTER TABLE recordings ALTER COLUMN original_file_name SET NOT NULL;

COMMIT;
