from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .upload_storage import LocalObjectStorage


class LifecycleRepository(Protocol):
    def timeline(
        self, user_id: UUID, content_type: str | None, member_id: UUID | None,
        date_from: datetime | None, date_to: datetime | None, limit: int,
    ) -> list[dict]: ...
    def create_share(self, user_id: UUID, creation_id: UUID, hours: int) -> dict | None: ...
    def list_shares(self, user_id: UUID) -> list[dict]: ...
    def revoke_share(self, user_id: UUID, share_id: UUID) -> dict | None: ...
    def resolve_share(self, token: str, count_access: bool = True) -> dict | None: ...
    def get_privacy_settings(self, user_id: UUID) -> dict | None: ...
    def update_privacy_settings(
        self, user_id: UUID, retention_days: int, share_hours: int, sharing_enabled: bool
    ) -> dict | None: ...
    def delete_creation(self, user_id: UUID, creation_id: UUID) -> dict | None: ...
    def delete_recording(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def delete_family(self, user_id: UUID, family_id: UUID) -> dict | None: ...
    def purge_expired_originals(self) -> dict: ...
    def metrics(self, user_id: UUID) -> dict | None: ...


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PostgresLifecycleRepository:
    def __init__(self, database_url: str, storage: LocalObjectStorage):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.storage = storage

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _member_ids(value) -> list[UUID]:
        return [item for item in (value or []) if item is not None]

    def timeline(
        self, user_id: UUID, content_type: str | None = None, member_id: UUID | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None, limit: int = 50,
    ) -> list[dict]:
        with self._connect() as connection:
            recordings = connection.execute(
                """
                SELECT recording.id, recording.title, recording.scene_type,
                       recording.status::text, recording.created_at,
                       recording.id AS recording_id,
                       array_agg(DISTINCT segment.family_member_id)
                         FILTER (WHERE segment.family_member_id IS NOT NULL) AS member_ids
                FROM recordings recording
                JOIN families family ON family.id=recording.family_id
                LEFT JOIN transcript_segments segment ON segment.recording_id=recording.id
                WHERE family.owner_user_id=%s AND recording.status <> 'DELETED'
                GROUP BY recording.id
                """,
                (user_id,),
            ).fetchall()
            moments = connection.execute(
                """
                SELECT work.id, work.title, work.quote AS theme, work.audio_status AS status,
                       work.created_at, work.recording_id,
                       array_agg(DISTINCT segment.family_member_id)
                         FILTER (WHERE segment.family_member_id IS NOT NULL) AS member_ids
                FROM highlight_works work
                JOIN families family ON family.id=work.family_id
                LEFT JOIN transcript_segments segment ON segment.recording_id=work.recording_id
                  AND segment.start_ms<work.end_ms AND segment.end_ms>work.start_ms
                WHERE family.owner_user_id=%s AND work.deleted_at IS NULL
                GROUP BY work.id
                """,
                (user_id,),
            ).fetchall()
            creations = connection.execute(
                """
                SELECT creation.id, creation.title, creation.type::text AS creation_type,
                       creation.status::text, creation.created_at, moment.recording_id,
                       array_agg(DISTINCT segment.family_member_id)
                         FILTER (WHERE segment.family_member_id IS NOT NULL) AS member_ids
                FROM creations creation
                JOIN families family ON family.id=creation.family_id
                JOIN moments moment ON moment.id=creation.moment_id
                LEFT JOIN transcript_segments segment ON segment.recording_id=moment.recording_id
                WHERE family.owner_user_id=%s
                GROUP BY creation.id, moment.recording_id
                """,
                (user_id,),
            ).fetchall()

        items: list[dict] = []
        for row in recordings:
            items.append({
                "id": row["id"], "kind": "recording", "title": row["title"],
                "subtitle": row.get("scene_type") or "家庭录音", "status": row["status"],
                "created_at": row["created_at"], "recording_id": row["recording_id"],
                "target_path": f"/recordings/{row['id']}",
                "member_ids": self._member_ids(row.get("member_ids")),
            })
        for row in moments:
            items.append({
                "id": row["id"], "kind": "moment", "title": row["title"],
                "subtitle": row.get("theme") or "家庭高光", "status": row["status"],
                "created_at": row["created_at"], "recording_id": row["recording_id"],
                "target_path": f"/highlights/{row['id']}",
                "member_ids": self._member_ids(row.get("member_ids")),
            })
        for row in creations:
            kind = row["creation_type"].lower()
            items.append({
                "id": row["id"], "kind": kind, "title": row.get("title") or "家庭作品",
                "subtitle": "四格家庭漫画" if kind == "comic" else "家庭播客",
                "status": row["status"], "created_at": row["created_at"],
                "recording_id": row["recording_id"],
                "target_path": f"/{kind}s/{row['id']}",
                "member_ids": self._member_ids(row.get("member_ids")),
            })
        if content_type:
            items = [item for item in items if item["kind"] == content_type]
        if member_id:
            items = [item for item in items if member_id in item["member_ids"]]
        if date_from:
            items = [item for item in items if item["created_at"] >= date_from]
        if date_to:
            items = [item for item in items if item["created_at"] <= date_to]
        return sorted(items, key=lambda item: (item["created_at"], str(item["id"])), reverse=True)[:limit]

    def create_share(self, user_id: UUID, creation_id: UUID, hours: int) -> dict | None:
        token = secrets.token_urlsafe(32)
        with self._connect() as connection:
            creation = connection.execute(
                """
                SELECT creation.family_id, creation.type::text AS creation_type,
                       creation.title
                FROM creations creation JOIN families family ON family.id=creation.family_id
                WHERE creation.id=%s AND family.owner_user_id=%s
                  AND creation.status='COMPLETED'
                """,
                (creation_id, user_id),
            ).fetchone()
            if creation is None:
                return None
            settings = connection.execute(
                """
                INSERT INTO family_privacy_settings (family_id) VALUES (%s)
                ON CONFLICT (family_id) DO UPDATE SET family_id=EXCLUDED.family_id
                RETURNING sharing_enabled
                """,
                (creation["family_id"],),
            ).fetchone()
            if not settings["sharing_enabled"]:
                return None
            share = connection.execute(
                """
                INSERT INTO creation_shares (
                  family_id, creation_id, created_by_user_id, token_hash, expires_at
                ) VALUES (%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    creation["family_id"], creation_id, user_id, _token_hash(token),
                    datetime.now(UTC) + timedelta(hours=hours),
                ),
            ).fetchone()
            return {
                **share,
                "creation_type": creation["creation_type"],
                "title": creation["title"],
                "token": token,
            }

    def list_shares(self, user_id: UUID) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT share.*, creation.type::text AS creation_type, creation.title
                FROM creation_shares share
                JOIN creations creation ON creation.id=share.creation_id
                JOIN families family ON family.id=share.family_id
                WHERE family.owner_user_id=%s ORDER BY share.created_at DESC
                """,
                (user_id,),
            ).fetchall()

    def revoke_share(self, user_id: UUID, share_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE creation_shares share SET revoked_at=COALESCE(share.revoked_at,now())
                FROM families family, creations creation
                WHERE share.id=%s AND family.id=share.family_id AND family.owner_user_id=%s
                  AND creation.id=share.creation_id
                RETURNING share.*,creation.type::text AS creation_type,creation.title
                """,
                (share_id, user_id),
            ).fetchone()

    def resolve_share(self, token: str, count_access: bool = True) -> dict | None:
        digest = _token_hash(token)
        with self._connect() as connection:
            share = connection.execute(
                """
                SELECT share.*, creation.type::text AS creation_type, creation.title,
                       creation.object_key, creation.metadata, moment.recording_id
                FROM creation_shares share
                JOIN creations creation ON creation.id=share.creation_id
                JOIN moments moment ON moment.id=creation.moment_id
                WHERE share.token_hash=%s AND share.revoked_at IS NULL
                  AND share.expires_at > now() AND creation.status='COMPLETED'
                """,
                (digest,),
            ).fetchone()
            if share is None:
                return None
            if count_access:
                connection.execute(
                    """
                    UPDATE creation_shares SET access_count=access_count+1,
                      last_accessed_at=now() WHERE id=%s
                    """,
                    (share["id"],),
                )
            panels = []
            if share["creation_type"] == "COMIC":
                panels = connection.execute(
                    """
                    SELECT panel_index,narration,dialogue,asset_url,asset_variant,crop_x,crop_y
                    FROM comic_panels WHERE creation_id=%s ORDER BY panel_index
                    """,
                    (share["creation_id"],),
                ).fetchall()
            return {**share, "panels": panels}

    def get_privacy_settings(self, user_id: UUID) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                "SELECT id FROM families WHERE owner_user_id=%s", (user_id,)
            ).fetchone()
            if family is None:
                return None
            return connection.execute(
                """
                INSERT INTO family_privacy_settings (family_id) VALUES (%s)
                ON CONFLICT (family_id) DO UPDATE SET family_id=EXCLUDED.family_id
                RETURNING *
                """,
                (family["id"],),
            ).fetchone()

    def update_privacy_settings(
        self, user_id: UUID, retention_days: int, share_hours: int, sharing_enabled: bool
    ) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                "SELECT id FROM families WHERE owner_user_id=%s", (user_id,)
            ).fetchone()
            if family is None:
                return None
            settings = connection.execute(
                """
                INSERT INTO family_privacy_settings (
                  family_id,recording_retention_days,share_default_hours,sharing_enabled
                ) VALUES (%s,%s,%s,%s)
                ON CONFLICT (family_id) DO UPDATE SET
                  recording_retention_days=EXCLUDED.recording_retention_days,
                  share_default_hours=EXCLUDED.share_default_hours,
                  sharing_enabled=EXCLUDED.sharing_enabled,updated_at=now()
                RETURNING *
                """,
                (family["id"], retention_days, share_hours, sharing_enabled),
            ).fetchone()
            connection.execute(
                """
                UPDATE recordings SET delete_at=created_at+(%s * interval '1 day')
                WHERE family_id=%s AND object_key IS NOT NULL
                """,
                (retention_days, family["id"]),
            )
            if not sharing_enabled:
                connection.execute(
                    """
                    UPDATE creation_shares SET revoked_at=COALESCE(revoked_at,now())
                    WHERE family_id=%s
                    """,
                    (family["id"],),
                )
                connection.execute(
                    """
                    UPDATE podcast_shares SET revoked_at=COALESCE(revoked_at,now())
                    WHERE family_id=%s
                    """,
                    (family["id"],),
                )
            return settings

    @staticmethod
    def _delete_result(target_id: UUID, scope: str, keys: list[str]) -> dict:
        return {
            "target_id": target_id, "scope": scope, "deleted": True,
            "object_count": len(keys), "completed_at": datetime.now(UTC), "object_keys": keys,
        }

    def _delete_objects(self, keys: list[str]) -> None:
        for key in dict.fromkeys(item for item in keys if item):
            self.storage.delete(key)

    @staticmethod
    def _creation_object_keys(creation: dict) -> list[str]:
        object_key = creation.get("object_key")
        if not object_key:
            return []
        if creation.get("creation_type") == "PODCAST":
            match = re.fullmatch(r"(.+)/v\d+\.mp3", object_key)
            if match:
                return [
                    f"{match.group(1)}/v{version}.mp3"
                    for version in range(1, int(creation.get("version") or 1) + 1)
                ]
        return [object_key]

    def delete_creation(self, user_id: UUID, creation_id: UUID) -> dict | None:
        with self._connect() as connection:
            storybook_keys = connection.execute(
                """
                SELECT asset.object_key FROM storybook_audio_assets asset
                JOIN storybook_versions version ON version.id=asset.storybook_version_id
                JOIN storybooks book ON book.id=version.storybook_id
                WHERE book.comic_id=%s
                """,
                (creation_id,),
            ).fetchall()
            storybook_track_keys = connection.execute(
                """
                SELECT track.object_key FROM storybook_experience_tracks track
                JOIN storybook_versions version ON version.id=track.storybook_version_id
                JOIN storybooks book ON book.id=version.storybook_id
                WHERE book.comic_id=%s AND track.object_key IS NOT NULL
                """,
                (creation_id,),
            ).fetchall()
            creation = connection.execute(
                """
                DELETE FROM creations creation USING families family
                WHERE creation.id=%s AND family.id=creation.family_id
                  AND family.owner_user_id=%s
                RETURNING creation.family_id,creation.object_key,
                          creation.type::text AS creation_type,creation.version
                """,
                (creation_id, user_id),
            ).fetchone()
            if creation is None:
                return None
            keys = self._creation_object_keys(creation)
            keys.extend(row["object_key"] for row in storybook_keys)
            keys.extend(row["object_key"] for row in storybook_track_keys)
            connection.execute(
                """
                INSERT INTO deletion_audits (
                  family_id,requested_by_user_id,scope,target_id,result,completed_at
                ) VALUES (%s,%s,'CREATION',%s,'COMPLETED',now())
                """,
                (creation["family_id"], user_id, creation_id),
            )
        self._delete_objects(keys)
        return self._delete_result(creation_id, "CREATION", keys)

    def delete_recording(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            recording = connection.execute(
                """
                SELECT recording.* FROM recordings recording
                JOIN families family ON family.id=recording.family_id
                WHERE recording.id=%s AND family.owner_user_id=%s FOR UPDATE
                """,
                (recording_id, user_id),
            ).fetchone()
            if recording is None:
                return None
            creation_keys = connection.execute(
                """
                SELECT creation.object_key,creation.type::text AS creation_type,
                       creation.version
                FROM creations creation
                JOIN moments moment ON moment.id=creation.moment_id
                WHERE moment.recording_id=%s AND creation.object_key IS NOT NULL
                """,
                (recording_id,),
            ).fetchall()
            storybook_keys = connection.execute(
                """
                SELECT object_key FROM storybook_audio_assets
                WHERE source_recording_id=%s
                """,
                (recording_id,),
            ).fetchall()
            storybook_track_keys = connection.execute(
                """
                SELECT object_key FROM storybook_experience_tracks
                WHERE source_recording_id=%s AND object_key IS NOT NULL
                """,
                (recording_id,),
            ).fetchall()
            highlight_keys = connection.execute(
                """
                SELECT work.audio_object_key,cover.object_key AS cover_object_key,
                       cover.thumbnail_object_key
                FROM highlight_works work
                LEFT JOIN highlight_cover_assets cover ON cover.highlight_work_id=work.id
                WHERE work.recording_id=%s
                """,
                (recording_id,),
            ).fetchall()
            keys = ([recording["object_key"]] if recording.get("object_key") else [])
            for creation in creation_keys:
                keys.extend(self._creation_object_keys(creation))
            keys.extend(row["object_key"] for row in storybook_keys)
            keys.extend(row["object_key"] for row in storybook_track_keys)
            for highlight in highlight_keys:
                keys.extend(value for value in highlight.values() if value)
            connection.execute("DELETE FROM recordings WHERE id=%s", (recording_id,))
            connection.execute(
                """
                INSERT INTO deletion_audits (
                  family_id,requested_by_user_id,scope,target_id,result,completed_at
                ) VALUES (%s,%s,'RECORDING',%s,'COMPLETED',now())
                """,
                (recording["family_id"], user_id, recording_id),
            )
        self._delete_objects(keys)
        return self._delete_result(recording_id, "RECORDING", keys)

    def delete_family(self, user_id: UUID, family_id: UUID) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                "SELECT id FROM families WHERE id=%s AND owner_user_id=%s FOR UPDATE",
                (family_id, user_id),
            ).fetchone()
            if family is None:
                return None
            recording_rows = connection.execute(
                """
                SELECT object_key FROM recordings WHERE family_id=%s AND object_key IS NOT NULL
                """,
                (family_id,),
            ).fetchall()
            creation_rows = connection.execute(
                """
                SELECT object_key,type::text AS creation_type,version
                FROM creations WHERE family_id=%s AND object_key IS NOT NULL
                """,
                (family_id,),
            ).fetchall()
            storybook_rows = connection.execute(
                "SELECT object_key FROM storybook_audio_assets WHERE family_id=%s",
                (family_id,),
            ).fetchall()
            storybook_track_rows = connection.execute(
                """
                SELECT object_key FROM storybook_experience_tracks
                WHERE family_id=%s AND object_key IS NOT NULL
                """,
                (family_id,),
            ).fetchall()
            keys = [row["object_key"] for row in recording_rows]
            for creation in creation_rows:
                keys.extend(self._creation_object_keys(creation))
            keys.extend(row["object_key"] for row in storybook_rows)
            keys.extend(row["object_key"] for row in storybook_track_rows)
            connection.execute("DELETE FROM families WHERE id=%s", (family_id,))
            connection.execute(
                """
                INSERT INTO deletion_audits (
                  family_id,requested_by_user_id,scope,target_id,result,completed_at
                ) VALUES (%s,%s,'FAMILY',%s,'COMPLETED',now())
                """,
                (family_id, user_id, family_id),
            )
        self._delete_objects(keys)
        return self._delete_result(family_id, "FAMILY", keys)

    def purge_expired_originals(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id,family_id,object_key FROM recordings
                WHERE delete_at<=now() AND object_key IS NOT NULL FOR UPDATE SKIP LOCKED
                """
            ).fetchall()
            for row in rows:
                self.storage.delete(row["object_key"])
                connection.execute(
                    "UPDATE recordings SET object_key=NULL,delete_at=NULL,updated_at=now() WHERE id=%s",
                    (row["id"],),
                )
                connection.execute(
                    """
                    INSERT INTO deletion_audits (
                      family_id,scope,target_id,result,completed_at
                    ) VALUES (%s,'ORIGINAL_AUDIO_EXPIRY',%s,'COMPLETED',now())
                    """,
                    (row["family_id"], row["id"]),
                )
        return {"purged": len(rows)}

    def metrics(self, user_id: UUID) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                "SELECT id FROM families WHERE owner_user_id=%s", (user_id,)
            ).fetchone()
            if family is None:
                return None
            family_id = family["id"]
            recording = connection.execute(
                """
                SELECT count(*) AS total,
                  count(*) FILTER (WHERE status NOT IN ('FAILED','CREATED','UPLOADING')) AS uploaded
                FROM recordings WHERE family_id=%s
                """,
                (family_id,),
            ).fetchone()
            jobs = connection.execute(
                """
                SELECT count(*) AS total,
                  count(*) FILTER (WHERE stage='READY_FOR_SELECTION') AS succeeded,
                  percentile_cont(0.95) WITHIN GROUP (
                    ORDER BY extract(epoch FROM (completed_at-started_at))
                  ) FILTER (WHERE completed_at IS NOT NULL AND started_at IS NOT NULL) AS p95
                FROM jobs WHERE family_id=%s AND type='RECORDING_PIPELINE'
                """,
                (family_id,),
            ).fetchone()
            creations = connection.execute(
                """
                SELECT count(*) AS total,count(*) FILTER (WHERE status='COMPLETED') AS succeeded
                FROM creations WHERE family_id=%s
                """,
                (family_id,),
            ).fetchone()
            deletions = connection.execute(
                """
                SELECT count(*) AS total,count(*) FILTER (WHERE result='COMPLETED') AS succeeded
                FROM deletion_audits WHERE family_id=%s
                """,
                (family_id,),
            ).fetchone()
            active_shares = connection.execute(
                """
                SELECT count(*) AS count FROM creation_shares
                WHERE family_id=%s AND revoked_at IS NULL AND expires_at>now()
                """,
                (family_id,),
            ).fetchone()["count"]

        def rate(row):
            return round(row["succeeded"] / row["total"], 4) if row["total"] else None

        return {
            "recordings_total": recording["total"],
            "upload_success_rate": (
                round(recording["uploaded"] / recording["total"], 4)
                if recording["total"] else None
            ),
            "analysis_success_rate": rate(jobs),
            "generation_success_rate": rate(creations),
            "processing_p95_seconds": round(float(jobs["p95"]), 3) if jobs["p95"] else None,
            "deletion_success_rate": rate(deletions),
            "active_shares": active_shares,
        }
