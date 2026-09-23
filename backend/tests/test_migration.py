from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_initial_migration_contains_all_core_entities() -> None:
    sql = (ROOT / "database/migrations/0001_initial.sql").read_text(encoding="utf-8")
    for table in (
        "users",
        "families",
        "family_members",
        "recordings",
        "transcript_segments",
        "moments",
        "creations",
        "jobs",
        "deletion_audits",
    ):
        assert f"CREATE TABLE {table}" in sql


def test_family_owned_content_carries_family_id() -> None:
    sql = (ROOT / "database/migrations/0001_initial.sql").read_text(encoding="utf-8")
    for table in ("recordings", "transcript_segments", "moments", "creations", "jobs"):
        block = sql.split(f"CREATE TABLE {table}", 1)[1].split(");", 1)[0]
        assert "family_id uuid NOT NULL" in block


def test_core_entities_have_stable_ids_and_timestamps() -> None:
    sql = (ROOT / "database/migrations/0001_initial.sql").read_text(encoding="utf-8")
    for table in (
        "users",
        "families",
        "family_members",
        "recordings",
        "transcript_segments",
        "moments",
        "creations",
        "jobs",
    ):
        block = sql.split(f"CREATE TABLE {table}", 1)[1].split(");", 1)[0]
        assert "id uuid PRIMARY KEY" in block
        assert "created_at timestamptz NOT NULL" in block
        assert "updated_at timestamptz NOT NULL" in block


def test_down_migration_covers_all_tables() -> None:
    sql = (ROOT / "database/migrations/0001_initial.down.sql").read_text(encoding="utf-8")
    assert sql.count("DROP TABLE IF EXISTS") == 9


def test_sound_postcard_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0023_sound_postcards.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0023_sound_postcards.down.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE highlight_reactions" in up
    assert "CREATE TABLE highlight_comments" in up
    assert "ADD COLUMN aspect_ratio" in up
    assert "DROP TABLE IF EXISTS highlight_comments" in down
    assert "DROP COLUMN IF EXISTS aspect_ratio" in down


def test_family_gramophone_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0024_family_gramophone.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0024_family_gramophone.down.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE podcast_reactions" in up
    assert "CREATE TABLE podcast_comments" in up
    assert "ALTER TABLE podcast_cover_assets" in up
    assert "DROP TABLE IF EXISTS podcast_comments" in down
    assert "DROP COLUMN IF EXISTS aspect_ratio" in down


def test_identity_family_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0002_identity_family.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0002_identity_family.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE UNIQUE INDEX uq_families_owner_user" in up
    assert "DROP INDEX IF EXISTS uq_families_owner_user" in down


def test_web_identity_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0003_web_identity.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0003_web_identity.down.sql").read_text(
        encoding="utf-8"
    )
    assert "ADD COLUMN phone_hash" in up
    assert "CREATE UNIQUE INDEX uq_users_phone_hash" in up
    assert "DROP COLUMN IF EXISTS phone_hash" in down


def test_recording_upload_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0004_recording_upload.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0004_recording_upload.down.sql").read_text(
        encoding="utf-8"
    )
    for column in ("file_size", "original_file_name", "error_code"):
        assert f"ADD COLUMN {column}" in up
        assert f"DROP COLUMN IF EXISTS {column}" in down


def test_async_job_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0005_async_jobs.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0005_async_jobs.down.sql").read_text(encoding="utf-8")
    for column in (
        "heartbeat_at", "started_at", "completed_at", "dead_lettered_at",
        "queue_attempted_at", "execution_token",
    ):
        assert f"ADD COLUMN {column}" in up
        assert f"DROP COLUMN IF EXISTS {column}" in down
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in up


def test_transcription_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0006_transcription.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0006_transcription.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE recording_speaker_mappings" in up
    assert "ADD COLUMN original_text" in up
    assert "ADD COLUMN transcript_revision" in up
    assert "DROP TABLE IF EXISTS recording_speaker_mappings" in down
    assert "DROP COLUMN IF EXISTS transcript_revision" in down


def test_moment_feedback_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0007_moments.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0007_moments.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE moment_feedback" in up
    assert "ADD COLUMN selection_state" in up
    assert "ADD COLUMN score_breakdown" in up
    assert "DROP TABLE IF EXISTS moment_feedback" in down
    assert "DROP COLUMN IF EXISTS selection_state" in down


def test_comic_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0008_comics.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0008_comics.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE comic_panels" in up
    assert "ADD COLUMN metadata" in up
    assert "DROP TABLE IF EXISTS comic_panels" in down
    assert "DROP COLUMN IF EXISTS metadata" in down


def test_podcast_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0009_podcasts.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0009_podcasts.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE podcast_moments" in up
    assert "CREATE TABLE podcast_segments" in up
    assert "DROP TABLE IF EXISTS podcast_segments" in down
    assert "DROP TABLE IF EXISTS podcast_moments" in down


def test_timeline_privacy_migration_is_reversible_and_hashes_share_tokens() -> None:
    up = (ROOT / "database/migrations/0010_timeline_privacy.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0010_timeline_privacy.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE family_privacy_settings" in up
    assert "CREATE TABLE creation_shares" in up
    assert "token_hash text NOT NULL UNIQUE" in up
    assert "recording_retention_days smallint NOT NULL DEFAULT 7" in up
    assert "UPDATE recordings recording" in up
    assert "DROP TABLE IF EXISTS creation_shares" in down
    assert "DROP TABLE IF EXISTS family_privacy_settings" in down


def test_storybook_migration_is_reversible_and_versioned() -> None:
    up = (ROOT / "database/migrations/0011_storybooks.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0011_storybooks.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE storybooks" in up
    assert "CREATE TABLE storybook_versions" in up
    assert "UNIQUE (storybook_id, version)" in up
    assert "UNIQUE (storybook_id, source_comic_version)" in up
    assert "manifest jsonb NOT NULL" in up
    assert "DROP TABLE IF EXISTS storybook_versions" in down
    assert "DROP TABLE IF EXISTS storybooks" in down


def test_storybook_audio_migration_is_reversible_and_traceable() -> None:
    up = (ROOT / "database/migrations/0012_storybook_audio_assets.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0012_storybook_audio_assets.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE storybook_audio_assets" in up
    assert "source_segment_id uuid" in up
    assert "original_start_ms integer NOT NULL" in up
    assert "UNIQUE (storybook_version_id, page_index, kind)" in up
    assert "DROP TABLE IF EXISTS storybook_audio_assets" in down


def test_storybook_experience_track_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0013_storybook_experience_tracks.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0013_storybook_experience_tracks.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE storybook_experience_tracks" in up
    assert "storyline jsonb NOT NULL" in up
    assert "cues jsonb NOT NULL" in up
    assert "UNIQUE (storybook_version_id)" in up
    assert "DROP TABLE IF EXISTS storybook_experience_tracks" in down


def test_mobile_media_intake_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0019_mobile_media_intake.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0019_mobile_media_intake.down.sql").read_text(
        encoding="utf-8"
    )
    for source_type in ("audio_upload", "video_upload", "mobile_recording", "recording_bean"):
        assert source_type in up
    assert "ADD COLUMN source_type" in up
    assert "DROP COLUMN IF EXISTS source_type" in down


def test_podcast_material_capacity_migration_is_reversible() -> None:
    up = (ROOT / "database/migrations/0020_podcast_material_capacity.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0020_podcast_material_capacity.down.sql").read_text(encoding="utf-8")
    assert "position BETWEEN 1 AND 10" in up
    assert "position BETWEEN 1 AND 3" in down


def test_storybook_story_plan_migration_is_reversible_and_versioned() -> None:
    up = (ROOT / "database/migrations/0014_storybook_story_plans.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0014_storybook_story_plans.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE storybook_story_plans" in up
    assert "source_story jsonb NOT NULL" in up
    assert "director_script jsonb NOT NULL" in up
    assert "UNIQUE (storybook_version_id)" in up
    assert "DROP TABLE IF EXISTS storybook_story_plans" in down


def test_podcast_mvp_migration_is_reversible_versioned_and_traceable() -> None:
    up = (ROOT / "database/migrations/0015_podcast_mvp.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0015_podcast_mvp.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE podcast_projects" in up
    assert "CREATE TABLE podcast_versions" in up
    assert "CREATE TABLE podcast_material_sets" in up
    assert "CREATE TABLE podcast_materials" in up
    assert "source_segment_id uuid NOT NULL" in up
    assert "original_text text NOT NULL" in up
    assert "confirmed_text text NOT NULL" in up
    assert "CREATE TABLE podcast_plans" in up
    assert "CREATE TABLE podcast_cover_assets" in up
    assert "CREATE TABLE podcast_tags" in up
    assert "CREATE TABLE podcast_version_tags" in up
    assert "UNIQUE (project_id, version)" in up
    assert "DROP TABLE IF EXISTS podcast_version_tags" in down
    assert "DROP TABLE IF EXISTS podcast_projects" in down


def test_podcast_material_confirmation_migration_is_reversible() -> None:
    up = (
        ROOT / "database/migrations/0016_podcast_material_confirmation.sql"
    ).read_text(encoding="utf-8")
    down = (
        ROOT / "database/migrations/0016_podcast_material_confirmation.down.sql"
    ).read_text(encoding="utf-8")
    assert "ADD COLUMN transcript_revision" in up
    assert "ADD COLUMN confirmed_by_user_id" in up
    assert "ADD COLUMN source_moment_id" in up
    assert "CREATE UNIQUE INDEX idx_podcast_projects_recording" in up
    assert "DROP INDEX IF EXISTS idx_podcast_projects_recording" in down
    assert "DROP COLUMN IF EXISTS source_moment_id" in down


def test_podcast_render_job_migration_is_reversible_and_idempotent() -> None:
    up = (ROOT / "database/migrations/0017_podcast_render_jobs.sql").read_text(
        encoding="utf-8"
    )
    down = (ROOT / "database/migrations/0017_podcast_render_jobs.down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE podcast_render_jobs" in up
    assert "idempotency_key text NOT NULL UNIQUE" in up
    assert "render_metadata jsonb NOT NULL" in up
    assert "DROP TABLE IF EXISTS podcast_render_jobs" in down


def test_podcast_share_migration_is_reversible_private_and_minimal() -> None:
    up = (ROOT / "database/migrations/0018_podcast_shares.sql").read_text(encoding="utf-8")
    down = (ROOT / "database/migrations/0018_podcast_shares.down.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE podcast_shares" in up
    assert "token_hash text NOT NULL UNIQUE" in up
    assert "CREATE TABLE podcast_share_access_logs" in up
    assert "share_id uuid NOT NULL" in up
    assert "DROP TABLE IF EXISTS podcast_share_access_logs" in down
    assert "DROP TABLE IF EXISTS podcast_shares" in down
