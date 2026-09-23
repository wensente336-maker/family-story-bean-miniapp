BEGIN;

DROP INDEX IF EXISTS idx_podcast_projects_recording;
ALTER TABLE podcast_materials DROP COLUMN IF EXISTS source_moment_id;
ALTER TABLE podcast_material_sets
  DROP COLUMN IF EXISTS confirmed_by_user_id,
  DROP COLUMN IF EXISTS transcript_revision;

COMMIT;
