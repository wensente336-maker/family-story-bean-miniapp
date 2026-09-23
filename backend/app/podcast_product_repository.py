from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


SYSTEM_TAGS = (
    "家庭日常", "亲子时光", "欢乐瞬间", "成长记录",
    "节日团聚", "旅行见闻", "睡前故事", "长辈往事",
)


class PodcastProductRepository(Protocol):
    def get_by_recording(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def update(self, user_id: UUID, recording_id: UUID, title: str, description: str, tags: list[str]) -> dict | None: ...
    def save_cover(self, user_id: UUID, recording_id: UUID, cover: dict) -> tuple[dict, list[str]] | None: ...
    def delete_cover(self, user_id: UUID, recording_id: UUID) -> list[str] | None: ...
    def list_by_tag(self, user_id: UUID, tag: str | None = None) -> list[dict]: ...
    def list_trash(self, user_id: UUID) -> list[dict]: ...
    def set_deleted(self, user_id: UUID, recording_id: UUID, deleted: bool) -> dict | None: ...
    def set_like(self, user_id: UUID, version_id: UUID, liked: bool) -> dict | None: ...
    def list_comments(self, user_id: UUID, version_id: UUID, cursor: UUID | None, limit: int) -> dict | None: ...
    def create_comment(self, user_id: UUID, version_id: UUID, body: str) -> dict | None: ...
    def update_comment(self, user_id: UUID, comment_id: UUID, body: str) -> dict | None: ...
    def delete_comment(self, user_id: UUID, comment_id: UUID) -> dict | None: ...


class PostgresPodcastProductRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _version(connection, user_id: UUID, recording_id: UUID, trashed: bool = False) -> dict | None:
        return connection.execute(
            """
            SELECT version.*, project.recording_id, project.deleted_at
            FROM podcast_versions version
            JOIN podcast_projects project ON project.id=version.project_id
            JOIN families family ON family.id=version.family_id
            WHERE project.recording_id=%s AND family.owner_user_id=%s
              AND version.status='COMPLETED'
              AND (project.deleted_at IS NOT NULL)=%s
            ORDER BY (version.version=project.current_version) DESC,
                     version.version DESC LIMIT 1
            FOR UPDATE OF project
            """,
            (recording_id, user_id, trashed),
        ).fetchone()

    @staticmethod
    def _ensure_system_tags(connection, family_id: UUID) -> None:
        for name in SYSTEM_TAGS:
            connection.execute(
                """
                INSERT INTO podcast_tags (family_id,name,kind) VALUES (%s,%s,'system')
                ON CONFLICT (family_id,name) DO NOTHING
                """,
                (family_id, name),
            )

    @classmethod
    def _payload(cls, connection, version: dict, user_id: UUID | None = None) -> dict:
        cls._ensure_system_tags(connection, version["family_id"])
        cover = connection.execute(
            "SELECT * FROM podcast_cover_assets WHERE podcast_version_id=%s",
            (version["id"],),
        ).fetchone()
        tags = connection.execute(
            """
            SELECT tag.id,tag.name,tag.kind FROM podcast_version_tags link
            JOIN podcast_tags tag ON tag.id=link.tag_id
            WHERE link.podcast_version_id=%s ORDER BY link.position
            """,
            (version["id"],),
        ).fetchall()
        available = connection.execute(
            "SELECT id,name,kind FROM podcast_tags WHERE family_id=%s ORDER BY kind DESC,name",
            (version["family_id"],),
        ).fetchall()
        sources = connection.execute(
            """
            SELECT material.id AS material_id,material.source_segment_id,
                   material.speaker_label,material.start_ms,material.end_ms,
                   material.confirmed_text
            FROM podcast_material_sets material_set
            JOIN podcast_materials material ON material.material_set_id=material_set.id
            WHERE material_set.podcast_version_id=%s ORDER BY material.position
            """,
            (version["id"],),
        ).fetchall()
        metadata = version.get("render_metadata") or {}
        chapters = []
        for index, item in enumerate(metadata.get("timeline") or [], start=1):
            chapters.append({
                "segment_index": int(item.get("segment_index") or index),
                "kind": item.get("kind") if item.get("kind") in {"narration", "original"} else "narration",
                "label": str(item.get("label") or f"第 {index} 段"),
                "start_ms": max(0, int(item.get("start_ms") or 0)),
                "end_ms": max(0, int(item.get("end_ms") or 0)),
                "source_segment_id": item.get("source_segment_id"),
            })
        interaction = connection.execute(
            """SELECT
              (SELECT count(*) FROM podcast_reactions WHERE podcast_version_id=%s AND reaction_type='LIKE') AS like_count,
              (SELECT count(*) FROM podcast_comments WHERE podcast_version_id=%s AND status='ACTIVE') AS comment_count,
              EXISTS(SELECT 1 FROM podcast_reactions WHERE podcast_version_id=%s AND user_id=%s AND reaction_type='LIKE') AS liked_by_me""",
            (version["id"], version["id"], version["id"], user_id),
        ).fetchone() if user_id else {"like_count": 0, "comment_count": 0, "liked_by_me": False}
        return {
            "podcast_version_id": version["id"],
            "recording_id": version["recording_id"],
            "version": version["version"],
            "status": "COMPLETED",
            "title": version["title"],
            "description": version["description"],
            "duration_ms": max(0, int(metadata.get("duration_ms") or 0)),
            "render_mode": metadata.get("render_mode") if metadata.get("render_mode") in {"narrated", "original_only"} else "original_only",
            "audio_asset_fingerprint": version.get("render_fingerprint") or str(version["object_key"]),
            "cover": cover,
            "tags": tags,
            "available_tags": available,
            "chapters": chapters,
            "sources": sources,
            "created_at": version["created_at"],
            "updated_at": version["updated_at"],
            "deleted_at": version.get("deleted_at"),
            **interaction,
            "can_edit": True,
            "can_comment": version.get("deleted_at") is None,
        }

    def get_by_recording(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            version = self._version(connection, user_id, recording_id)
            return self._payload(connection, version, user_id) if version else None

    def update(
        self, user_id: UUID, recording_id: UUID, title: str, description: str, tags: list[str]
    ) -> dict | None:
        with self._connect() as connection:
            version = self._version(connection, user_id, recording_id)
            if version is None:
                return None
            self._ensure_system_tags(connection, version["family_id"])
            updated = connection.execute(
                """
                UPDATE podcast_versions SET title=%s,description=%s,updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (title.strip(), description.strip(), version["id"]),
            ).fetchone()
            connection.execute(
                "UPDATE podcast_projects SET title=%s,updated_at=now() WHERE id=%s",
                (title.strip(), version["project_id"]),
            )
            connection.execute(
                "DELETE FROM podcast_version_tags WHERE podcast_version_id=%s",
                (version["id"],),
            )
            for position, name in enumerate(tags, start=1):
                kind = "system" if name in SYSTEM_TAGS else "custom"
                tag = connection.execute(
                    """
                    INSERT INTO podcast_tags (family_id,name,kind) VALUES (%s,%s,%s)
                    ON CONFLICT (family_id,name) DO UPDATE SET name=EXCLUDED.name
                    RETURNING id
                    """,
                    (version["family_id"], name, kind),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO podcast_version_tags (family_id,podcast_version_id,tag_id,position)
                    VALUES (%s,%s,%s,%s)
                    """,
                    (version["family_id"], version["id"], tag["id"], position),
                )
            return self._payload(connection, {**updated, "recording_id": recording_id}, user_id)

    def save_cover(
        self, user_id: UUID, recording_id: UUID, cover: dict
    ) -> tuple[dict, list[str]] | None:
        with self._connect() as connection:
            version = self._version(connection, user_id, recording_id)
            if version is None:
                return None
            old = connection.execute(
                "SELECT object_key,thumbnail_object_key FROM podcast_cover_assets WHERE podcast_version_id=%s",
                (version["id"],),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO podcast_cover_assets (
                  family_id,podcast_version_id,object_key,thumbnail_object_key,
                  media_type,width,height,byte_size,sha256,aspect_ratio,layout_version,focal_x,focal_y
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (podcast_version_id) DO UPDATE SET
                  object_key=EXCLUDED.object_key,
                  thumbnail_object_key=EXCLUDED.thumbnail_object_key,
                  media_type=EXCLUDED.media_type,width=EXCLUDED.width,height=EXCLUDED.height,
                  byte_size=EXCLUDED.byte_size,sha256=EXCLUDED.sha256,
                  aspect_ratio=EXCLUDED.aspect_ratio,layout_version=EXCLUDED.layout_version,
                  focal_x=EXCLUDED.focal_x,focal_y=EXCLUDED.focal_y,updated_at=now()
                """,
                (
                    version["family_id"], version["id"], cover["object_key"],
                    cover["thumbnail_object_key"], cover["media_type"], cover["width"],
                    cover["height"], cover["byte_size"], cover["sha256"], cover["aspect_ratio"],
                    cover["layout_version"], cover["focal_x"], cover["focal_y"],
                ),
            )
            connection.execute(
                "UPDATE podcast_versions SET updated_at=now() WHERE id=%s", (version["id"],)
            )
            refreshed = self._version(connection, user_id, recording_id)
            old_keys = [value for value in (old or {}).values() if value]
            return self._payload(connection, refreshed, user_id), old_keys

    def delete_cover(self, user_id: UUID, recording_id: UUID) -> list[str] | None:
        with self._connect() as connection:
            version = self._version(connection, user_id, recording_id)
            if version is None:
                return None
            old = connection.execute(
                """
                DELETE FROM podcast_cover_assets WHERE podcast_version_id=%s
                RETURNING object_key,thumbnail_object_key
                """,
                (version["id"],),
            ).fetchone()
            connection.execute(
                "UPDATE podcast_versions SET updated_at=now() WHERE id=%s", (version["id"],)
            )
            return [value for value in (old or {}).values() if value]

    def list_by_tag(self, user_id: UUID, tag: str | None = None) -> list[dict]:
        with self._connect() as connection:
            if tag:
                rows = connection.execute(
                    """
                    SELECT DISTINCT project.recording_id FROM podcast_versions version
                    JOIN podcast_projects project ON project.id=version.project_id
                    JOIN families family ON family.id=version.family_id
                    JOIN podcast_version_tags link ON link.podcast_version_id=version.id
                    JOIN podcast_tags tag ON tag.id=link.tag_id
                    WHERE family.owner_user_id=%s AND version.status='COMPLETED'
                      AND project.deleted_at IS NULL
                      AND tag.name=%s
                    ORDER BY project.recording_id
                    """,
                    (user_id, tag),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT DISTINCT project.recording_id FROM podcast_versions version
                    JOIN podcast_projects project ON project.id=version.project_id
                    JOIN families family ON family.id=version.family_id
                    WHERE family.owner_user_id=%s AND version.status='COMPLETED'
                      AND project.deleted_at IS NULL
                    ORDER BY project.recording_id
                    """,
                    (user_id,),
                ).fetchall()
            result = []
            for row in rows:
                version = self._version(connection, user_id, row["recording_id"])
                if version:
                    result.append(self._payload(connection, version, user_id))
            return result

    def list_trash(self, user_id: UUID) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT project.recording_id FROM podcast_projects project
                JOIN families family ON family.id=project.family_id
                WHERE family.owner_user_id=%s AND project.deleted_at IS NOT NULL
                ORDER BY project.deleted_at DESC""", (user_id,),
            ).fetchall()
            result = []
            for row in rows:
                version = self._version(connection, user_id, row["recording_id"], trashed=True)
                if version:
                    result.append(self._payload(connection, version, user_id))
            return result

    @staticmethod
    def _owned_version(connection, user_id: UUID, version_id: UUID) -> dict | None:
        return connection.execute(
            """SELECT version.id,version.family_id FROM podcast_versions version
            JOIN podcast_projects project ON project.id=version.project_id
            JOIN families family ON family.id=version.family_id
            WHERE version.id=%s AND family.owner_user_id=%s AND project.deleted_at IS NULL
              AND version.status='COMPLETED'""", (version_id, user_id),
        ).fetchone()

    def set_like(self, user_id: UUID, version_id: UUID, liked: bool) -> dict | None:
        with self._connect() as connection:
            version = self._owned_version(connection, user_id, version_id)
            if not version:
                return None
            if liked:
                connection.execute(
                    """INSERT INTO podcast_reactions(family_id,podcast_version_id,user_id)
                    VALUES(%s,%s,%s) ON CONFLICT(podcast_version_id,user_id,reaction_type) DO NOTHING""",
                    (version["family_id"], version_id, user_id),
                )
            else:
                connection.execute(
                    "DELETE FROM podcast_reactions WHERE podcast_version_id=%s AND user_id=%s AND reaction_type='LIKE'",
                    (version_id, user_id),
                )
            count = connection.execute(
                "SELECT count(*) AS value FROM podcast_reactions WHERE podcast_version_id=%s AND reaction_type='LIKE'",
                (version_id,),
            ).fetchone()["value"]
            return {"podcast_version_id": version_id, "liked": liked, "like_count": count}

    @staticmethod
    def _comment_payload(row: dict, user_id: UUID) -> dict:
        return {**row, "can_edit": row.get("author_user_id") == user_id, "can_delete": True}

    def list_comments(self, user_id: UUID, version_id: UUID, cursor: UUID | None, limit: int) -> dict | None:
        with self._connect() as connection:
            if not self._owned_version(connection, user_id, version_id):
                return None
            rows = connection.execute(
                """SELECT comment.* FROM podcast_comments comment
                WHERE comment.podcast_version_id=%s AND comment.status='ACTIVE'
                  AND (%s::uuid IS NULL OR (comment.created_at,comment.id) <
                    (SELECT created_at,id FROM podcast_comments WHERE id=%s AND podcast_version_id=%s))
                ORDER BY comment.created_at DESC,comment.id DESC LIMIT %s""",
                (version_id, cursor, cursor, version_id, limit + 1),
            ).fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            return {"items": [self._comment_payload(row, user_id) for row in rows],
                    "next_cursor": rows[-1]["id"] if has_more and rows else None}

    def create_comment(self, user_id: UUID, version_id: UUID, body: str) -> dict | None:
        with self._connect() as connection:
            version = self._owned_version(connection, user_id, version_id)
            if not version:
                return None
            author = connection.execute(
                "SELECT nickname FROM family_members WHERE family_id=%s ORDER BY created_at,id LIMIT 1",
                (version["family_id"],),
            ).fetchone()
            row = connection.execute(
                """INSERT INTO podcast_comments(family_id,podcast_version_id,author_user_id,author_name,body)
                VALUES(%s,%s,%s,%s,%s) RETURNING *""",
                (version["family_id"], version_id, user_id, author["nickname"] if author else "家庭成员", body.strip()),
            ).fetchone()
            return self._comment_payload(row, user_id)

    def update_comment(self, user_id: UUID, comment_id: UUID, body: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """UPDATE podcast_comments comment SET body=%s,updated_at=now()
                FROM podcast_versions version,podcast_projects project,families family
                WHERE comment.id=%s AND comment.author_user_id=%s AND comment.status='ACTIVE'
                  AND version.id=comment.podcast_version_id AND project.id=version.project_id
                  AND project.deleted_at IS NULL AND family.id=comment.family_id AND family.owner_user_id=%s
                RETURNING comment.*""", (body.strip(), comment_id, user_id, user_id),
            ).fetchone()
            return self._comment_payload(row, user_id) if row else None

    def delete_comment(self, user_id: UUID, comment_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """UPDATE podcast_comments comment SET status='DELETED',deleted_at=now(),updated_at=now()
                FROM podcast_versions version,families family
                WHERE comment.id=%s AND comment.status='ACTIVE' AND version.id=comment.podcast_version_id
                  AND family.id=comment.family_id AND family.owner_user_id=%s
                RETURNING comment.id,comment.podcast_version_id""", (comment_id, user_id),
            ).fetchone()

    def set_deleted(self, user_id: UUID, recording_id: UUID, deleted: bool) -> dict | None:
        # Share creation takes the same project lock: a concurrent share cannot
        # slip past the revocation transaction and become live after restoration.
        with self._connect() as connection:
            project = connection.execute(
                """SELECT project.* FROM podcast_projects project
                JOIN families family ON family.id=project.family_id
                WHERE project.recording_id=%s AND family.owner_user_id=%s
                  AND EXISTS (SELECT 1 FROM podcast_versions version
                    WHERE version.project_id=project.id AND version.status='COMPLETED')
                FOR UPDATE OF project""", (recording_id, user_id),
            ).fetchone()
            if project is None:
                return None
            if bool(project["deleted_at"]) == deleted:
                return {"recording_id": recording_id, "deleted_at": project["deleted_at"]}
            row = connection.execute(
                """UPDATE podcast_projects SET
                deleted_at=CASE WHEN %s THEN now() ELSE NULL END,
                deleted_by_user_id=CASE WHEN %s THEN %s::uuid ELSE NULL END
                WHERE id=%s RETURNING deleted_at""",
                (deleted, deleted, user_id, project["id"]),
            ).fetchone()
            if deleted:
                connection.execute(
                    """UPDATE podcast_shares share SET revoked_at=now()
                    FROM podcast_versions version
                    WHERE share.podcast_version_id=version.id
                      AND version.project_id=%s AND share.revoked_at IS NULL""",
                    (project["id"],),
                )
            connection.execute(
                """INSERT INTO deletion_audits
                (family_id,requested_by_user_id,scope,target_id,result,completed_at)
                VALUES (%s,%s,%s,%s,'COMPLETED',now())""",
                (project["family_id"], user_id,
                 "podcast_trash" if deleted else "podcast_restore", project["id"]),
            )
            return {"recording_id": recording_id, "deleted_at": row["deleted_at"]}
