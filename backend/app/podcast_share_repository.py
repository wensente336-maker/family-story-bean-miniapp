from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PodcastShareNotAllowed(RuntimeError):
    pass


class PodcastShareRepository(Protocol):
    def create(self, user_id: UUID, recording_id: UUID, hours: int) -> dict | None: ...
    def list_for_user(self, user_id: UUID, recording_id: UUID | None = None) -> list[dict]: ...
    def revoke(self, user_id: UUID, share_id: UUID) -> dict | None: ...
    def resolve(self, token: str, count_access: bool = True) -> dict | None: ...


class PostgresPodcastShareRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create(self, user_id: UUID, recording_id: UUID, hours: int) -> dict | None:
        token = secrets.token_urlsafe(32)
        with self._connect() as connection:
            project = connection.execute(
                """SELECT project.id FROM podcast_projects project
                JOIN families family ON family.id=project.family_id
                WHERE project.recording_id=%s AND family.owner_user_id=%s
                  AND project.deleted_at IS NULL FOR UPDATE OF project""",
                (recording_id, user_id),
            ).fetchone()
            if project is None:
                return None
            version = connection.execute(
                """
                SELECT version.id AS podcast_version_id,version.family_id,version.title,
                       project.recording_id,
                       EXISTS (
                         SELECT 1 FROM podcast_material_sets material_set
                         WHERE material_set.podcast_version_id=version.id
                           AND material_set.status='CONFIRMED'
                       ) AS material_set_confirmed,
                       NOT EXISTS (
                         SELECT 1 FROM podcast_material_sets material_set
                         JOIN podcast_materials material
                           ON material.material_set_id=material_set.id
                         WHERE material_set.podcast_version_id=version.id
                           AND material.share_allowed=false
                       ) AS materials_share_allowed,
                       EXISTS (
                         SELECT 1
                         FROM podcast_plans plan
                         WHERE plan.podcast_version_id=version.id
                           AND plan.status='CONFIRMED'
                           AND COALESCE(
                             (plan.plan->>'external_share_allowed')::boolean,false
                           )=true
                       ) AS plan_share_allowed
                FROM podcast_versions version
                JOIN podcast_projects project ON project.id=version.project_id
                JOIN families family ON family.id=version.family_id
                WHERE project.recording_id=%s AND family.owner_user_id=%s
                  AND project.deleted_at IS NULL
                  AND version.status='COMPLETED' AND version.object_key IS NOT NULL
                ORDER BY (version.version=project.current_version) DESC,
                         version.version DESC LIMIT 1
                """,
                (recording_id, user_id),
            ).fetchone()
            if version is None:
                return None
            if (
                not version["material_set_confirmed"]
                or not version["materials_share_allowed"]
                or not version["plan_share_allowed"]
            ):
                raise PodcastShareNotAllowed(
                    "podcast contains family-only audio material"
                )
            privacy = connection.execute(
                """
                INSERT INTO family_privacy_settings (family_id) VALUES (%s)
                ON CONFLICT (family_id) DO UPDATE SET family_id=EXCLUDED.family_id
                RETURNING sharing_enabled
                """,
                (version["family_id"],),
            ).fetchone()
            if not privacy["sharing_enabled"]:
                return None
            share = connection.execute(
                """
                INSERT INTO podcast_shares (
                  family_id,podcast_version_id,created_by_user_id,token_hash,expires_at
                ) VALUES (%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    version["family_id"], version["podcast_version_id"], user_id,
                    token_hash(token), datetime.now(UTC) + timedelta(hours=hours),
                ),
            ).fetchone()
            return {**share, **version, "token": token}

    def list_for_user(self, user_id: UUID, recording_id: UUID | None = None) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT share.*,version.title,project.recording_id
                FROM podcast_shares share
                JOIN podcast_versions version ON version.id=share.podcast_version_id
                JOIN podcast_projects project ON project.id=version.project_id
                JOIN families family ON family.id=share.family_id
                WHERE family.owner_user_id=%s AND (%s::uuid IS NULL OR project.recording_id=%s)
                ORDER BY share.created_at DESC
                """,
                (user_id, recording_id, recording_id),
            ).fetchall()

    def revoke(self, user_id: UUID, share_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE podcast_shares share SET revoked_at=COALESCE(share.revoked_at,now())
                FROM families family,podcast_versions version,podcast_projects project
                WHERE share.id=%s AND family.id=share.family_id
                  AND family.owner_user_id=%s AND version.id=share.podcast_version_id
                  AND project.id=version.project_id
                RETURNING share.*,version.title,project.recording_id
                """,
                (share_id, user_id),
            ).fetchone()

    def resolve(self, token: str, count_access: bool = True) -> dict | None:
        with self._connect() as connection:
            share = connection.execute(
                """
                SELECT share.*,version.title,version.description,version.object_key,
                       version.render_metadata,project.recording_id,
                       cover.object_key AS cover_object_key
                FROM podcast_shares share
                JOIN podcast_versions version ON version.id=share.podcast_version_id
                JOIN podcast_projects project ON project.id=version.project_id
                LEFT JOIN podcast_cover_assets cover ON cover.podcast_version_id=version.id
                WHERE share.token_hash=%s AND share.revoked_at IS NULL
                  AND project.deleted_at IS NULL
                  AND share.expires_at>now() AND version.status='COMPLETED'
                  AND version.object_key IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM podcast_material_sets material_set
                    WHERE material_set.podcast_version_id=version.id
                      AND material_set.status='CONFIRMED'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM podcast_material_sets material_set
                    JOIN podcast_materials material
                      ON material.material_set_id=material_set.id
                    WHERE material_set.podcast_version_id=version.id
                      AND material.share_allowed=false
                  )
                  AND EXISTS (
                    SELECT 1 FROM podcast_plans plan
                    WHERE plan.podcast_version_id=version.id
                      AND plan.status='CONFIRMED'
                      AND COALESCE(
                        (plan.plan->>'external_share_allowed')::boolean,false
                      )=true
                  )
                """,
                (token_hash(token),),
            ).fetchone()
            if share is None:
                return None
            if count_access:
                connection.execute(
                    """
                    UPDATE podcast_shares SET access_count=access_count+1,
                      last_accessed_at=now() WHERE id=%s
                    """,
                    (share["id"],),
                )
                connection.execute(
                    "INSERT INTO podcast_share_access_logs (share_id) VALUES (%s)",
                    (share["id"],),
                )
            tags = connection.execute(
                """
                SELECT tag.name FROM podcast_version_tags link
                JOIN podcast_tags tag ON tag.id=link.tag_id
                WHERE link.podcast_version_id=%s ORDER BY link.position
                """,
                (share["podcast_version_id"],),
            ).fetchall()
            return {**share, "tags": [item["name"] for item in tags]}
