BEGIN;

CREATE TABLE highlight_works (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  -- The work keeps its own quote and time range. The discovery candidate may be
  -- regenerated later without deleting the saved high-light work.
  source_moment_id uuid UNIQUE REFERENCES moments(id) ON DELETE SET NULL,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  title text NOT NULL,
  quote text NOT NULL,
  share_allowed boolean NOT NULL DEFAULT true,
  start_ms integer NOT NULL CHECK (start_ms >= 0),
  end_ms integer NOT NULL CHECK (end_ms > start_ms),
  audio_status text NOT NULL DEFAULT 'PENDING'
    CHECK (audio_status IN ('PENDING','READY','UNAVAILABLE','FAILED')),
  audio_object_key text,
  audio_failure_code text,
  deleted_at timestamptz,
  deleted_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT highlight_ready_audio CHECK (audio_status <> 'READY' OR audio_object_key IS NOT NULL)
);

CREATE TABLE highlight_cover_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  highlight_work_id uuid NOT NULL UNIQUE REFERENCES highlight_works(id) ON DELETE CASCADE,
  object_key text NOT NULL,
  thumbnail_object_key text NOT NULL,
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  byte_size integer NOT NULL CHECK (byte_size > 0 AND byte_size <= 5242880),
  sha256 text NOT NULL CHECK (length(sha256)=64),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE highlight_shares (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  highlight_work_id uuid NOT NULL REFERENCES highlight_works(id) ON DELETE CASCADE,
  created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  token_hash text NOT NULL UNIQUE CHECK (length(token_hash)=64),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  access_count integer NOT NULL DEFAULT 0 CHECK (access_count >= 0),
  last_accessed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT highlight_share_expiry CHECK (expires_at > created_at)
);

CREATE INDEX idx_highlight_works_family_created ON highlight_works(family_id,created_at DESC)
  WHERE deleted_at IS NULL;
CREATE INDEX idx_highlight_works_trash ON highlight_works(family_id,deleted_at DESC)
  WHERE deleted_at IS NOT NULL;
CREATE INDEX idx_highlight_shares_work ON highlight_shares(highlight_work_id,created_at DESC);
CREATE INDEX idx_highlight_shares_active_token ON highlight_shares(token_hash,expires_at)
  WHERE revoked_at IS NULL;

-- Existing confirmed podcast selections become stable high-glight works. Audio is
-- cut lazily on first list/detail access so this migration remains transactional.
INSERT INTO highlight_works (
  family_id,source_moment_id,recording_id,created_by_user_id,title,quote,share_allowed,start_ms,end_ms,created_at,updated_at
)
SELECT DISTINCT ON (material.source_moment_id)
  material.family_id,material.source_moment_id,material.source_recording_id,
  material_set.confirmed_by_user_id,moment.title,
  COALESCE(NULLIF(material.confirmed_text,''),moment.storyboard->>'highlight_quote',moment.title),
  material.share_allowed,material.start_ms,material.end_ms,
  COALESCE(material_set.confirmed_at,material_set.created_at),material_set.updated_at
FROM podcast_materials material
JOIN podcast_material_sets material_set ON material_set.id=material.material_set_id
JOIN moments moment ON moment.id=material.source_moment_id
WHERE material.source_moment_id IS NOT NULL AND material_set.status='CONFIRMED'
ORDER BY material.source_moment_id,material_set.confirmed_at DESC NULLS LAST
ON CONFLICT (source_moment_id) DO NOTHING;

COMMIT;
