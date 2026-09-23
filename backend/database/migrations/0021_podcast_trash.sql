BEGIN;
ALTER TABLE podcast_projects
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
  ADD COLUMN IF NOT EXISTS deleted_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_podcast_projects_trash
  ON podcast_projects(family_id, deleted_at DESC) WHERE deleted_at IS NOT NULL;
COMMIT;
