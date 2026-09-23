BEGIN;
-- Refuse to discard recovery state. Roll back the UI while retaining this
-- additive schema in production; do not deploy an API that ignores deleted_at.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM podcast_projects WHERE deleted_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Restore trashed projects explicitly before removing the trash schema';
  END IF;
END $$;
DROP INDEX IF EXISTS idx_podcast_projects_trash;
ALTER TABLE podcast_projects
  DROP COLUMN IF EXISTS deleted_by_user_id,
  DROP COLUMN IF EXISTS deleted_at;
COMMIT;
