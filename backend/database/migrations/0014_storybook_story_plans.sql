BEGIN;

CREATE TABLE storybook_story_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  storybook_version_id uuid NOT NULL REFERENCES storybook_versions(id) ON DELETE CASCADE,
  source_recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'CONFIRMED')),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  source_schema_version text NOT NULL,
  director_schema_version text NOT NULL,
  source_story jsonb NOT NULL,
  director_script jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (storybook_version_id)
);

CREATE INDEX idx_storybook_story_plans_family
  ON storybook_story_plans(family_id, updated_at DESC);

COMMIT;
