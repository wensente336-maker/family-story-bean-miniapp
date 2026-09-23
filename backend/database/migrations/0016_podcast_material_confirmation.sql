BEGIN;

ALTER TABLE podcast_material_sets
  ADD COLUMN transcript_revision integer NOT NULL DEFAULT 0 CHECK (transcript_revision >= 0),
  ADD COLUMN confirmed_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE podcast_materials
  ADD COLUMN source_moment_id uuid REFERENCES moments(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX idx_podcast_projects_recording
  ON podcast_projects(recording_id);

COMMIT;
