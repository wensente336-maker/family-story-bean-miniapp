BEGIN;

ALTER TABLE podcast_materials
  DROP CONSTRAINT IF EXISTS podcast_materials_position_check;

ALTER TABLE podcast_materials
  ADD CONSTRAINT podcast_materials_position_check CHECK (position BETWEEN 1 AND 10);

COMMIT;
