BEGIN;

CREATE TABLE podcast_shares (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  podcast_version_id uuid NOT NULL REFERENCES podcast_versions(id) ON DELETE CASCADE,
  created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  token_hash text NOT NULL UNIQUE CHECK (length(token_hash) = 64),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  access_count integer NOT NULL DEFAULT 0 CHECK (access_count >= 0),
  last_accessed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT podcast_share_expiry_after_creation CHECK (expires_at > created_at)
);

CREATE TABLE podcast_share_access_logs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  share_id uuid NOT NULL REFERENCES podcast_shares(id) ON DELETE CASCADE,
  accessed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_podcast_shares_version
  ON podcast_shares(podcast_version_id, created_at DESC);
CREATE INDEX idx_podcast_shares_active_token
  ON podcast_shares(token_hash, expires_at) WHERE revoked_at IS NULL;
CREATE INDEX idx_podcast_share_access_logs_share
  ON podcast_share_access_logs(share_id, accessed_at DESC);

COMMIT;
