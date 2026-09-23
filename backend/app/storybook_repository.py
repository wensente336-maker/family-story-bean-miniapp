from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SCHEMA_VERSION = "storybook-manifest-v1"
STORY_PAGE_TITLES = (
    "一颗会飞的西红柿",
    "番茄拿铁",
    "冠军事故现场",
    "今天最好记的事",
)


class StorybookRepository(Protocol):
    def create_or_refresh(self, user_id: UUID, comic_id: UUID) -> dict | None: ...
    def get_for_user(self, user_id: UUID, storybook_id: UUID) -> dict | None: ...
    def list_versions(self, user_id: UUID, storybook_id: UUID) -> list[dict] | None: ...
    def get_version(self, user_id: UUID, storybook_id: UUID, version: int) -> dict | None: ...
    def get_audio_context(self, user_id: UUID, storybook_id: UUID) -> dict | None: ...
    def list_audio_assets(self, storybook_version_id: UUID) -> list[dict]: ...
    def save_audio_asset(self, asset: dict) -> dict: ...
    def mark_audio_ready(self, storybook_id: UUID) -> None: ...
    def get_experience_track(self, storybook_version_id: UUID) -> dict | None: ...
    def save_experience_track(self, track: dict) -> dict: ...
    def get_story_source_context(self, user_id: UUID, storybook_id: UUID) -> dict | None: ...
    def get_story_plan(self, storybook_version_id: UUID) -> dict | None: ...
    def save_story_plan(self, plan: dict) -> dict: ...
    def invalidate_experience_track(self, storybook_version_id: UUID) -> str | None: ...


class PostgresStorybookRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _title(comic: dict, panels: list[dict]) -> str:
        if any(
            "西红柿" in (panel.get("dialogue") or "")
            or "奶奶家" in (panel.get("dialogue") or "")
            for panel in panels
        ):
            return "会飞的西红柿"
        return comic["title"]

    @classmethod
    def build_manifest(cls, comic: dict, panels: list[dict]) -> dict:
        title = cls._title(comic, panels)
        pages = [{
            "index": 0,
            "type": "cover",
            "title": title,
            "narration": f"这是一本由家人真实声音做成的故事书。{title}",
            "panel_index": panels[0]["panel_index"] if panels else None,
            "panel_version": panels[0]["version"] if panels else None,
            "clip": None,
        }]
        for index, panel in enumerate(panels, start=1):
            clip = None
            if (
                panel.get("source_segment_id")
                and panel.get("clip_start_ms") is not None
                and panel.get("clip_end_ms") is not None
            ):
                clip = {
                    "source_segment_id": str(panel["source_segment_id"]),
                    "start_ms": panel["clip_start_ms"],
                    "end_ms": panel["clip_end_ms"],
                }
            pages.append({
                "index": index,
                "type": "story",
                "title": STORY_PAGE_TITLES[index - 1]
                if index <= len(STORY_PAGE_TITLES)
                else f"第 {panel['panel_index']} 页",
                "narration": panel["narration"],
                "panel_index": panel["panel_index"],
                "panel_version": panel["version"],
                "clip": clip,
            })
        last_panel = panels[-1] if panels else None
        pages.append({
            "index": len(pages),
            "type": "ending",
            "title": "家人的笑声，就是故事的封底",
            "narration": "一顿普通的晚餐，因为一颗西红柿，成了一家人会记得很久的快乐时刻。",
            "panel_index": last_panel["panel_index"] if last_panel else None,
            "panel_version": last_panel["version"] if last_panel else None,
            "clip": None,
        })
        return {
            "schema_version": SCHEMA_VERSION,
            "source_comic_id": str(comic["id"]),
            "source_comic_version": comic["version"],
            "title": title,
            "page_count": len(pages),
            "audio": {
                "background_mode": "client-synthesized",
                "page_turn_mode": "client-synthesized",
                "narration_mode": "browser-speech",
                "highlight_source": "recording-source-segments",
            },
            "pages": pages,
        }

    @staticmethod
    def _panels(connection, comic_id: UUID) -> list[dict]:
        return connection.execute(
            """
            SELECT panel.*, segment.start_ms AS clip_start_ms,
                   segment.end_ms AS clip_end_ms
            FROM comic_panels panel
            LEFT JOIN transcript_segments segment ON segment.id=panel.source_segment_id
            WHERE panel.creation_id=%s
            ORDER BY panel.panel_index
            """,
            (comic_id,),
        ).fetchall()

    @staticmethod
    def _payload(book: dict, version: dict, recording_id: UUID) -> dict:
        return {
            **book,
            "recording_id": recording_id,
            "schema_version": version["schema_version"],
            "source_comic_version": version["source_comic_version"],
            "manifest": version["manifest"],
        }

    def create_or_refresh(self, user_id: UUID, comic_id: UUID) -> dict | None:
        with self._connect() as connection:
            comic = connection.execute(
                """
                SELECT creation.*, moment.recording_id FROM creations creation
                JOIN families family ON family.id=creation.family_id
                JOIN moments moment ON moment.id=creation.moment_id
                WHERE creation.id=%s AND creation.type='COMIC'
                  AND family.owner_user_id=%s
                FOR UPDATE
                """,
                (comic_id, user_id),
            ).fetchone()
            if comic is None:
                return None
            panels = self._panels(connection, comic_id)
            manifest = self.build_manifest(comic, panels)
            book = connection.execute(
                "SELECT * FROM storybooks WHERE comic_id=%s FOR UPDATE",
                (comic_id,),
            ).fetchone()
            if book is None:
                book = connection.execute(
                    """
                    INSERT INTO storybooks (
                      family_id, comic_id, title, status, current_version
                    ) VALUES (%s,%s,%s,'DRAFT',1)
                    RETURNING *
                    """,
                    (comic["family_id"], comic_id, manifest["title"]),
                ).fetchone()
                version_number = 1
            else:
                existing = connection.execute(
                    """
                    SELECT * FROM storybook_versions
                    WHERE storybook_id=%s AND source_comic_version=%s
                    """,
                    (book["id"], comic["version"]),
                ).fetchone()
                if existing:
                    return self._payload(book, existing, comic["recording_id"])
                version_number = book["current_version"] + 1
                book = connection.execute(
                    """
                    UPDATE storybooks SET title=%s, current_version=%s, updated_at=now()
                    WHERE id=%s RETURNING *
                    """,
                    (manifest["title"], version_number, book["id"]),
                ).fetchone()
            version = connection.execute(
                """
                INSERT INTO storybook_versions (
                  family_id, storybook_id, version, schema_version,
                  source_comic_version, manifest
                ) VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    comic["family_id"], book["id"], version_number,
                    SCHEMA_VERSION, comic["version"], Jsonb(manifest),
                ),
            ).fetchone()
            return self._payload(book, version, comic["recording_id"])

    def get_for_user(self, user_id: UUID, storybook_id: UUID) -> dict | None:
        with self._connect() as connection:
            book = connection.execute(
                """
                SELECT book.*, moment.recording_id FROM storybooks book
                JOIN families family ON family.id=book.family_id
                JOIN creations comic ON comic.id=book.comic_id
                JOIN moments moment ON moment.id=comic.moment_id
                WHERE book.id=%s AND family.owner_user_id=%s
                """,
                (storybook_id, user_id),
            ).fetchone()
            if book is None:
                return None
            version = connection.execute(
                """
                SELECT * FROM storybook_versions
                WHERE storybook_id=%s AND version=%s
                """,
                (storybook_id, book["current_version"]),
            ).fetchone()
            return self._payload(book, version, book["recording_id"]) if version else None

    def list_versions(self, user_id: UUID, storybook_id: UUID) -> list[dict] | None:
        with self._connect() as connection:
            owned = connection.execute(
                """
                SELECT 1 FROM storybooks book
                JOIN families family ON family.id=book.family_id
                WHERE book.id=%s AND family.owner_user_id=%s
                """,
                (storybook_id, user_id),
            ).fetchone()
            if owned is None:
                return None
            return connection.execute(
                """
                SELECT version, schema_version, source_comic_version, created_at
                FROM storybook_versions WHERE storybook_id=%s ORDER BY version DESC
                """,
                (storybook_id,),
            ).fetchall()

    def get_version(self, user_id: UUID, storybook_id: UUID, version: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT version.storybook_id, version.version, version.schema_version,
                       version.source_comic_version, version.manifest, version.created_at
                FROM storybook_versions version
                JOIN storybooks book ON book.id=version.storybook_id
                JOIN families family ON family.id=book.family_id
                WHERE version.storybook_id=%s AND version.version=%s
                  AND family.owner_user_id=%s
                """,
                (storybook_id, version, user_id),
            ).fetchone()
            return row

    def get_audio_context(self, user_id: UUID, storybook_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT book.id AS storybook_id, book.family_id, book.current_version,
                       version.id AS storybook_version_id, version.manifest,
                       recording.id AS source_recording_id,
                       recording.object_key AS source_object_key,
                       recording.media_type AS source_media_type,
                       moment.storyboard, comic.metadata AS comic_metadata
                FROM storybooks book
                JOIN families family ON family.id=book.family_id
                JOIN storybook_versions version
                  ON version.storybook_id=book.id AND version.version=book.current_version
                JOIN creations comic ON comic.id=book.comic_id
                JOIN moments moment ON moment.id=comic.moment_id
                JOIN recordings recording ON recording.id=moment.recording_id
                WHERE book.id=%s AND family.owner_user_id=%s
                """,
                (storybook_id, user_id),
            ).fetchone()

    def get_story_source_context(self, user_id: UUID, storybook_id: UUID) -> dict | None:
        with self._connect() as connection:
            context = connection.execute(
                """
                SELECT book.id AS storybook_id, book.family_id, book.title,
                       book.current_version, version.id AS storybook_version_id,
                       version.manifest, recording.id AS source_recording_id,
                       recording.object_key AS source_object_key,
                       recording.media_type AS source_media_type,
                       moment.id AS moment_id, moment.start_ms AS moment_start_ms,
                       moment.end_ms AS moment_end_ms, moment.storyboard,
                       comic.metadata AS comic_metadata
                FROM storybooks book
                JOIN families family ON family.id=book.family_id
                JOIN storybook_versions version
                  ON version.storybook_id=book.id AND version.version=book.current_version
                JOIN creations comic ON comic.id=book.comic_id
                JOIN moments moment ON moment.id=comic.moment_id
                JOIN recordings recording ON recording.id=moment.recording_id
                WHERE book.id=%s AND family.owner_user_id=%s
                """,
                (storybook_id, user_id),
            ).fetchone()
            if context is None:
                return None
            segments = connection.execute(
                """
                SELECT segment.id, segment.speaker_key, segment.start_ms,
                       segment.end_ms, segment.text,
                       COALESCE(mapping.display_name, segment.speaker_key) AS speaker_name
                FROM transcript_segments segment
                LEFT JOIN recording_speaker_mappings mapping
                  ON mapping.recording_id=segment.recording_id
                 AND mapping.speaker_key=segment.speaker_key
                WHERE segment.recording_id=%s
                  AND segment.start_ms < %s AND segment.end_ms > %s
                ORDER BY segment.start_ms, segment.end_ms, segment.id
                """,
                (
                    context["source_recording_id"], context["moment_end_ms"],
                    context["moment_start_ms"],
                ),
            ).fetchall()
            return {**context, "transcript_segments": segments}

    def list_audio_assets(self, storybook_version_id: UUID) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT * FROM storybook_audio_assets
                WHERE storybook_version_id=%s ORDER BY page_index
                """,
                (storybook_version_id,),
            ).fetchall()

    def save_audio_asset(self, asset: dict) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                INSERT INTO storybook_audio_assets (
                  family_id, storybook_version_id, page_index, kind,
                  source_recording_id, source_segment_id, original_start_ms,
                  original_end_ms, object_key, media_type, duration_ms
                ) VALUES (%s,%s,%s,'ORIGINAL_CLIP',%s,%s,%s,%s,%s,'audio/mpeg',%s)
                ON CONFLICT (storybook_version_id, page_index, kind) DO UPDATE
                SET object_key=EXCLUDED.object_key, duration_ms=EXCLUDED.duration_ms
                RETURNING *
                """,
                (
                    asset["family_id"], asset["storybook_version_id"],
                    asset["page_index"], asset["source_recording_id"],
                    asset["source_segment_id"], asset["original_start_ms"],
                    asset["original_end_ms"], asset["object_key"], asset["duration_ms"],
                ),
            ).fetchone()

    def mark_audio_ready(self, storybook_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE storybooks SET status='READY', updated_at=now() WHERE id=%s",
                (storybook_id,),
            )

    def get_experience_track(self, storybook_version_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM storybook_experience_tracks WHERE storybook_version_id=%s",
                (storybook_version_id,),
            ).fetchone()

    def save_experience_track(self, track: dict) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                INSERT INTO storybook_experience_tracks (
                  family_id, storybook_version_id, source_recording_id, status,
                  object_key, duration_ms, storyline, cues, render_metadata
                ) VALUES (%s,%s,%s,'READY',%s,%s,%s,%s,%s)
                ON CONFLICT (storybook_version_id) DO UPDATE SET
                  status='READY', object_key=EXCLUDED.object_key,
                  duration_ms=EXCLUDED.duration_ms, storyline=EXCLUDED.storyline,
                  cues=EXCLUDED.cues, render_metadata=EXCLUDED.render_metadata,
                  error_detail=NULL, updated_at=now()
                RETURNING *
                """,
                (
                    track["family_id"], track["storybook_version_id"],
                    track["source_recording_id"], track["object_key"],
                    track["duration_ms"], Jsonb(track["storyline"]),
                    Jsonb(track["cues"]), Jsonb(track["render_metadata"]),
                ),
            ).fetchone()

    def get_story_plan(self, storybook_version_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT plan.*, version.storybook_id
                FROM storybook_story_plans plan
                JOIN storybook_versions version ON version.id=plan.storybook_version_id
                WHERE plan.storybook_version_id=%s
                """,
                (storybook_version_id,),
            ).fetchone()

    def save_story_plan(self, plan: dict) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                INSERT INTO storybook_story_plans (
                  family_id, storybook_version_id, source_recording_id, status,
                  revision, source_schema_version, director_schema_version,
                  source_story, director_script
                ) VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s)
                ON CONFLICT (storybook_version_id) DO UPDATE SET
                  status=EXCLUDED.status,
                  revision=storybook_story_plans.revision+1,
                  source_schema_version=EXCLUDED.source_schema_version,
                  director_schema_version=EXCLUDED.director_schema_version,
                  source_story=EXCLUDED.source_story,
                  director_script=EXCLUDED.director_script,
                  updated_at=now()
                RETURNING *, (
                  SELECT storybook_id FROM storybook_versions
                  WHERE id=storybook_story_plans.storybook_version_id
                ) AS storybook_id
                """,
                (
                    plan["family_id"], plan["storybook_version_id"],
                    plan["source_recording_id"], plan["status"],
                    plan["source_schema_version"], plan["director_schema_version"],
                    Jsonb(plan["source_story"]), Jsonb(plan["director_script"]),
                ),
            ).fetchone()

    def invalidate_experience_track(self, storybook_version_id: UUID) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                DELETE FROM storybook_experience_tracks
                WHERE storybook_version_id=%s RETURNING object_key
                """,
                (storybook_version_id,),
            ).fetchone()
            return row["object_key"] if row else None
