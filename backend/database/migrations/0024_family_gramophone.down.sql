BEGIN;
DROP TABLE IF EXISTS podcast_comments;
DROP TABLE IF EXISTS podcast_reactions;
ALTER TABLE podcast_cover_assets
  DROP COLUMN IF EXISTS focal_y,
  DROP COLUMN IF EXISTS focal_x,
  DROP COLUMN IF EXISTS layout_version,
  DROP COLUMN IF EXISTS aspect_ratio;
COMMIT;
