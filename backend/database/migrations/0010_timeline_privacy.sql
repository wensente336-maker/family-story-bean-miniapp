BEGIN;

CREATE TABLE family_privacy_settings (
  family_id uuid PRIMARY KEY REFERENCES families(id) ON DELETE CASCADE,
  recording_retention_days smallint NOT NULL DEFAULT 7
    CHECK (recording_retention_days BETWEEN 1 AND 30),
  share_default_hours smallint NOT NULL DEFAULT 24
    CHECK (share_default_hours BETWEEN 1 AND 168),
  sharing_enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO family_privacy_settings (family_id)
SELECT id FROM families
ON CONFLICT (family_id) DO NOTHING;

UPDATE recordings recording
SET delete_at = recording.created_at +
  (settings.recording_retention_days * interval '1 day')
FROM family_privacy_settings settings
WHERE settings.family_id = recording.family_id
  AND recording.object_key IS NOT NULL
  AND recording.delete_at IS NULL;

CREATE TABLE creation_shares (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  creation_id uuid NOT NULL REFERENCES creations(id) ON DELETE CASCADE,
  created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  access_count integer NOT NULL DEFAULT 0 CHECK (access_count >= 0),
  last_accessed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT share_expiry_after_creation CHECK (expires_at > created_at)
);

CREATE INDEX idx_creation_shares_creation
  ON creation_shares(creation_id, created_at DESC);
CREATE INDEX idx_creation_shares_active_token
  ON creation_shares(token_hash, expires_at) WHERE revoked_at IS NULL;
CREATE INDEX idx_recordings_expiry
  ON recordings(delete_at) WHERE delete_at IS NOT NULL AND object_key IS NOT NULL;

COMMIT;
