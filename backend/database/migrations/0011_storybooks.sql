BEGIN;

CREATE TABLE storybooks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  comic_id uuid NOT NULL REFERENCES creations(id) ON DELETE CASCADE,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'READY', 'ARCHIVED')),
  current_version integer NOT NULL DEFAULT 1 CHECK (current_version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (comic_id)
);

CREATE TABLE storybook_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  storybook_id uuid NOT NULL REFERENCES storybooks(id) ON DELETE CASCADE,
  version integer NOT NULL CHECK (version >= 1),
  schema_version text NOT NULL,
  source_comic_version integer NOT NULL CHECK (source_comic_version >= 1),
  manifest jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (storybook_id, version),
  UNIQUE (storybook_id, source_comic_version)
);

CREATE INDEX idx_storybooks_family_updated
  ON storybooks(family_id, updated_at DESC);
CREATE INDEX idx_storybook_versions_book
  ON storybook_versions(storybook_id, version DESC);

COMMIT;
