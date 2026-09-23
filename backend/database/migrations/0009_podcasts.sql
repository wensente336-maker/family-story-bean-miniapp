BEGIN;

CREATE TABLE podcast_moments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  creation_id uuid NOT NULL REFERENCES creations(id) ON DELETE CASCADE,
  moment_id uuid NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
  position smallint NOT NULL CHECK (position BETWEEN 1 AND 3),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (creation_id, position),
  UNIQUE (creation_id, moment_id)
);

CREATE TABLE podcast_segments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  creation_id uuid NOT NULL REFERENCES creations(id) ON DELETE CASCADE,
  segment_index smallint NOT NULL CHECK (segment_index >= 1),
  kind text NOT NULL CHECK (kind IN ('narration', 'original')),
  label text NOT NULL,
  text text NOT NULL,
  source_moment_id uuid REFERENCES moments(id) ON DELETE SET NULL,
  source_segment_id uuid REFERENCES transcript_segments(id) ON DELETE SET NULL,
  start_ms integer,
  end_ms integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT podcast_segment_source_bounds CHECK (
    (kind = 'narration' AND start_ms IS NULL AND end_ms IS NULL)
    OR
    (kind = 'original' AND start_ms >= 0 AND end_ms > start_ms)
  ),
  UNIQUE (creation_id, segment_index)
);

CREATE INDEX idx_podcast_moments_creation ON podcast_moments(creation_id, position);
CREATE INDEX idx_podcast_segments_creation ON podcast_segments(creation_id, segment_index);

COMMIT;
