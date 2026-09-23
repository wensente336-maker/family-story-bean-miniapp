BEGIN;

ALTER TABLE creations
  ADD COLUMN title text,
  ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE comic_panels (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  creation_id uuid NOT NULL REFERENCES creations(id) ON DELETE CASCADE,
  panel_index smallint NOT NULL CHECK (panel_index BETWEEN 1 AND 4),
  narration text NOT NULL,
  dialogue text,
  source_segment_id uuid REFERENCES transcript_segments(id) ON DELETE SET NULL,
  asset_url text NOT NULL,
  asset_variant text NOT NULL,
  crop_x smallint NOT NULL CHECK (crop_x IN (0, 1)),
  crop_y smallint NOT NULL CHECK (crop_y IN (0, 1)),
  prompt text NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (creation_id, panel_index)
);

CREATE INDEX idx_comic_panels_creation ON comic_panels(creation_id, panel_index);

COMMIT;
