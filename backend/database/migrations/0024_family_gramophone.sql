BEGIN;

ALTER TABLE podcast_cover_assets
  ADD COLUMN aspect_ratio text NOT NULL DEFAULT '1:1'
    CHECK (aspect_ratio IN ('1:1','3:4')),
  ADD COLUMN layout_version integer NOT NULL DEFAULT 1
    CHECK (layout_version IN (1,2)),
  ADD COLUMN focal_x numeric(4,3) NOT NULL DEFAULT 0.5
    CHECK (focal_x BETWEEN 0 AND 1),
  ADD COLUMN focal_y numeric(4,3) NOT NULL DEFAULT 0.5
    CHECK (focal_y BETWEEN 0 AND 1);

CREATE TABLE podcast_reactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reaction_type text NOT NULL DEFAULT 'LIKE' CHECK (reaction_type='LIKE'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(podcast_version_id,user_id,reaction_type)
);

CREATE TABLE podcast_comments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  author_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  author_name text NOT NULL,
  body text NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 500),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DELETED','HIDDEN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE INDEX idx_podcast_reactions_version ON podcast_reactions(podcast_version_id,created_at DESC);
CREATE INDEX idx_podcast_comments_version ON podcast_comments(podcast_version_id,created_at DESC,id DESC)
  WHERE status='ACTIVE';

COMMIT;
