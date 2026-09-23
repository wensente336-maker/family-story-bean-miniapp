BEGIN;

CREATE TABLE podcast_projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  created_by_user_id uuid NOT NULL REFERENCES users(id),
  title text NOT NULL DEFAULT '未命名家庭播客',
  current_version integer NOT NULL DEFAULT 1 CHECK (current_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE podcast_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  project_id uuid NOT NULL REFERENCES podcast_projects(id) ON DELETE CASCADE,
  legacy_creation_id uuid REFERENCES creations(id) ON DELETE SET NULL,
  version integer NOT NULL CHECK (version > 0),
  status text NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'CONFIRMED', 'GENERATING', 'COMPLETED', 'FAILED')),
  schema_version text NOT NULL DEFAULT 'podcast-v2',
  title text NOT NULL DEFAULT '未命名家庭播客',
  description text NOT NULL DEFAULT '',
  narrator_voice text,
  music_style text,
  object_key text,
  failure_code text,
  failure_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  confirmed_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, version),
  CONSTRAINT podcast_version_completed_asset CHECK (
    status <> 'COMPLETED' OR object_key IS NOT NULL
  )
);

CREATE TABLE podcast_material_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'CONFIRMED')),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  schema_version text NOT NULL DEFAULT 'podcast-material-v1',
  confirmed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (podcast_version_id)
);

CREATE TABLE podcast_materials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  material_set_id uuid NOT NULL REFERENCES podcast_material_sets(id) ON DELETE CASCADE,
  source_recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  source_segment_id uuid NOT NULL REFERENCES transcript_segments(id) ON DELETE RESTRICT,
  family_member_id uuid REFERENCES family_members(id) ON DELETE SET NULL,
  speaker_key text NOT NULL,
  speaker_label text NOT NULL,
  role text NOT NULL CHECK (role IN ('setup', 'highlight', 'response', 'ending')),
  position smallint NOT NULL CHECK (position BETWEEN 1 AND 3),
  start_ms integer NOT NULL CHECK (start_ms >= 0),
  end_ms integer NOT NULL CHECK (end_ms > start_ms AND end_ms <= 900000),
  original_text text NOT NULL,
  confirmed_text text NOT NULL,
  share_allowed boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (material_set_id, position),
  UNIQUE (material_set_id, source_segment_id)
);

CREATE TABLE podcast_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  material_set_id uuid NOT NULL REFERENCES podcast_material_sets(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'CONFIRMED')),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  schema_version text NOT NULL DEFAULT 'podcast-plan-v1',
  prompt_version text,
  model_version text,
  plan jsonb NOT NULL,
  confirmed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (podcast_version_id)
);

CREATE TABLE podcast_cover_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  object_key text NOT NULL,
  thumbnail_object_key text,
  media_type text NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png', 'image/webp')),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  byte_size integer NOT NULL CHECK (byte_size > 0 AND byte_size <= 5242880),
  sha256 text NOT NULL CHECK (length(sha256) = 64),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (podcast_version_id)
);

CREATE TABLE podcast_tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 30),
  kind text NOT NULL CHECK (kind IN ('system', 'custom')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (family_id, name)
);

CREATE TABLE podcast_version_tags (
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  tag_id uuid NOT NULL REFERENCES podcast_tags(id) ON DELETE CASCADE,
  position smallint NOT NULL CHECK (position BETWEEN 1 AND 5),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (podcast_version_id, tag_id),
  UNIQUE (podcast_version_id, position)
);

CREATE INDEX idx_podcast_projects_family_updated
  ON podcast_projects(family_id, updated_at DESC);
CREATE INDEX idx_podcast_versions_project_version
  ON podcast_versions(project_id, version DESC);
CREATE INDEX idx_podcast_versions_status
  ON podcast_versions(status, updated_at DESC);
CREATE INDEX idx_podcast_materials_set_position
  ON podcast_materials(material_set_id, position);
CREATE INDEX idx_podcast_tags_family_name
  ON podcast_tags(family_id, name);

COMMIT;
