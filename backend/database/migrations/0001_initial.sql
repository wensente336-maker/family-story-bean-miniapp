BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE job_stage AS ENUM (
  'CREATED', 'UPLOADING', 'UPLOADED', 'PREPROCESSING', 'TRANSCRIBING',
  'ANALYZING', 'READY_FOR_SELECTION', 'GENERATING',
  'COMPLETED', 'FAILED', 'CANCELLED', 'DELETED'
);

CREATE TYPE creation_type AS ENUM ('COMIC', 'PODCAST');

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  wechat_openid_hash text UNIQUE,
  status text NOT NULL DEFAULT 'PENDING',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE families (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE family_members (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  nickname text NOT NULL,
  character_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  voice_consent boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recordings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  created_by_user_id uuid NOT NULL REFERENCES users(id),
  title text NOT NULL,
  scene_type text,
  object_key text,
  media_type text,
  duration_ms integer CHECK (duration_ms IS NULL OR duration_ms BETWEEN 1 AND 900000),
  sha256 text,
  status job_stage NOT NULL DEFAULT 'CREATED',
  delete_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transcript_segments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  family_member_id uuid REFERENCES family_members(id) ON DELETE SET NULL,
  speaker_key text NOT NULL,
  start_ms integer NOT NULL CHECK (start_ms >= 0),
  end_ms integer NOT NULL CHECK (end_ms > start_ms),
  text text NOT NULL,
  confidence numeric(5,4) CHECK (confidence BETWEEN 0 AND 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE moments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  title text NOT NULL,
  theme text,
  score numeric(5,4) CHECK (score BETWEEN 0 AND 1),
  storyboard jsonb NOT NULL,
  selected boolean NOT NULL DEFAULT false,
  pipeline_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE creations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  moment_id uuid NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
  type creation_type NOT NULL,
  status job_stage NOT NULL DEFAULT 'CREATED',
  object_key text,
  version integer NOT NULL DEFAULT 1,
  pipeline_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (moment_id, type, version)
);

CREATE TABLE jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  recording_id uuid REFERENCES recordings(id) ON DELETE CASCADE,
  creation_id uuid REFERENCES creations(id) ON DELETE CASCADE,
  type text NOT NULL,
  stage job_stage NOT NULL DEFAULT 'CREATED',
  progress smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  retry_count smallint NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  idempotency_key text NOT NULL UNIQUE,
  pipeline_version text NOT NULL,
  error_code text,
  error_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE deletion_audits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid,
  requested_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  scope text NOT NULL,
  target_id uuid NOT NULL,
  result text NOT NULL,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_family_members_family ON family_members(family_id);
CREATE INDEX idx_recordings_family_created ON recordings(family_id, created_at DESC);
CREATE INDEX idx_transcript_recording_time ON transcript_segments(recording_id, start_ms);
CREATE INDEX idx_moments_recording_score ON moments(recording_id, score DESC);
CREATE INDEX idx_creations_family_created ON creations(family_id, created_at DESC);
CREATE INDEX idx_jobs_stage_created ON jobs(stage, created_at);

COMMIT;
