from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class FamilyRepository(Protocol):
    def upsert_user(self, openid_hash: str) -> dict: ...
    def upsert_phone_user(self, phone_hash: str) -> dict: ...
    def get_user(self, user_id: UUID) -> dict | None: ...
    def get_family_for_user(self, user_id: UUID) -> dict | None: ...
    def create_family(self, user_id: UUID, name: str, owner_nickname: str) -> dict: ...
    def get_family(self, user_id: UUID, family_id: UUID) -> dict | None: ...
    def rename_family(self, user_id: UUID, family_id: UUID, name: str) -> dict | None: ...
    def add_member(self, user_id: UUID, family_id: UUID, nickname: str) -> dict | None: ...
    def rename_member(
        self, user_id: UUID, family_id: UUID, member_id: UUID, nickname: str
    ) -> dict | None: ...
    def delete_member(
        self, user_id: UUID, family_id: UUID, member_id: UUID
    ) -> dict | None: ...


class RecordingRepository(Protocol):
    def create_recording(
        self, user_id: UUID, title: str, original_file_name: str, declared_size: int,
        declared_media_type: str | None, declared_sha256: str, source_type: str
    ) -> dict | None: ...
    def get_recording(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def get_recording_for_upload(self, recording_id: UUID) -> dict | None: ...
    def list_recordings(self, user_id: UUID) -> list[dict]: ...
    def mark_uploaded(
        self, user_id: UUID, recording_id: UUID, media_type: str, duration_ms: int,
        file_size: int, sha256: str
    ) -> dict | None: ...
    def mark_failed(self, recording_id: UUID, error_code: str) -> None: ...
    def delete_draft(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def latest_recording(self, user_id: UUID) -> dict | None: ...


class PostgresFamilyRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _family_payload(connection, family: dict) -> dict:
        members = connection.execute(
            """
            SELECT id, nickname, character_profile, voice_consent, created_at, updated_at
            FROM family_members WHERE family_id = %s ORDER BY created_at, id
            """,
            (family["id"],),
        ).fetchall()
        return {**family, "members": members}

    def upsert_user(self, openid_hash: str) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                INSERT INTO users (wechat_openid_hash, status)
                VALUES (%s, 'ACTIVE')
                ON CONFLICT (wechat_openid_hash) DO UPDATE
                SET status = 'ACTIVE', updated_at = now()
                RETURNING id, status, created_at, updated_at
                """,
                (openid_hash,),
            ).fetchone()

    def upsert_phone_user(self, phone_hash: str) -> dict:
        with self._connect() as connection:
            return connection.execute(
                """
                INSERT INTO users (phone_hash, status)
                VALUES (%s, 'ACTIVE')
                ON CONFLICT (phone_hash) WHERE phone_hash IS NOT NULL DO UPDATE
                SET status = 'ACTIVE', updated_at = now()
                RETURNING id, status, created_at, updated_at
                """,
                (phone_hash,),
            ).fetchone()

    def get_user(self, user_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT id, status, created_at, updated_at FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()

    def get_family_for_user(self, user_id: UUID) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                """
                SELECT id, owner_user_id, name, created_at, updated_at
                FROM families WHERE owner_user_id = %s ORDER BY created_at LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            return self._family_payload(connection, family) if family else None

    def create_family(self, user_id: UUID, name: str, owner_nickname: str) -> dict:
        with self._connect() as connection:
            family = connection.execute(
                """
                INSERT INTO families (owner_user_id, name) VALUES (%s, %s)
                RETURNING id, owner_user_id, name, created_at, updated_at
                """,
                (user_id, name),
            ).fetchone()
            connection.execute(
                "INSERT INTO family_members (family_id, nickname) VALUES (%s, %s)",
                (family["id"], owner_nickname),
            )
            return self._family_payload(connection, family)

    def get_family(self, user_id: UUID, family_id: UUID) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                """
                SELECT id, owner_user_id, name, created_at, updated_at
                FROM families WHERE id = %s AND owner_user_id = %s
                """,
                (family_id, user_id),
            ).fetchone()
            return self._family_payload(connection, family) if family else None

    def rename_family(self, user_id: UUID, family_id: UUID, name: str) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                """
                UPDATE families SET name = %s, updated_at = now()
                WHERE id = %s AND owner_user_id = %s
                RETURNING id, owner_user_id, name, created_at, updated_at
                """,
                (name, family_id, user_id),
            ).fetchone()
            return self._family_payload(connection, family) if family else None

    def add_member(self, user_id: UUID, family_id: UUID, nickname: str) -> dict | None:
        with self._connect() as connection:
            allowed = connection.execute(
                "SELECT 1 FROM families WHERE id = %s AND owner_user_id = %s",
                (family_id, user_id),
            ).fetchone()
            if not allowed:
                return None
            return connection.execute(
                """
                INSERT INTO family_members (family_id, nickname) VALUES (%s, %s)
                RETURNING id, nickname, character_profile, voice_consent, created_at, updated_at
                """,
                (family_id, nickname),
            ).fetchone()

    def rename_member(
        self, user_id: UUID, family_id: UUID, member_id: UUID, nickname: str
    ) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE family_members AS member SET nickname = %s, updated_at = now()
                FROM families AS family
                WHERE member.id = %s AND member.family_id = %s
                  AND family.id = member.family_id AND family.owner_user_id = %s
                RETURNING member.id, member.nickname, member.character_profile,
                          member.voice_consent, member.created_at, member.updated_at
                """,
                (nickname, member_id, family_id, user_id),
            ).fetchone()

    def delete_member(
        self, user_id: UUID, family_id: UUID, member_id: UUID
    ) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                """
                SELECT id, owner_user_id, name, created_at, updated_at
                FROM families WHERE id = %s AND owner_user_id = %s
                FOR UPDATE
                """,
                (family_id, user_id),
            ).fetchone()
            if family is None:
                return None
            creator = connection.execute(
                """
                SELECT id FROM family_members
                WHERE family_id = %s ORDER BY created_at, id LIMIT 1
                """,
                (family_id,),
            ).fetchone()
            if creator is None or creator["id"] == member_id:
                return None
            deleted = connection.execute(
                "DELETE FROM family_members WHERE id = %s AND family_id = %s RETURNING id",
                (member_id, family_id),
            ).fetchone()
            return self._family_payload(connection, family) if deleted else None


class PostgresRecordingRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_recording(
        self, user_id: UUID, title: str, original_file_name: str, declared_size: int,
        declared_media_type: str | None, declared_sha256: str, source_type: str
    ) -> dict | None:
        with self._connect() as connection:
            family = connection.execute(
                """
                SELECT family.id,
                  COALESCE(settings.recording_retention_days, 7) AS retention_days
                FROM families family
                LEFT JOIN family_privacy_settings settings ON settings.family_id=family.id
                WHERE family.owner_user_id=%s
                """,
                (user_id,),
            ).fetchone()
            if family is None:
                return None
            recording_id = connection.execute("SELECT gen_random_uuid() AS id").fetchone()["id"]
            object_key = f"families/{family['id']}/recordings/{recording_id}/source"
            return connection.execute(
                """
                INSERT INTO recordings (
                  id, family_id, created_by_user_id, title, object_key, media_type,
                  file_size, original_file_name, sha256, source_type, status, delete_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'UPLOADING', %s)
                RETURNING *
                """,
                (
                    recording_id, family["id"], user_id, title, object_key,
                    declared_media_type, declared_size, original_file_name,
                    declared_sha256, source_type,
                    datetime.now(UTC) + timedelta(days=family["retention_days"]),
                ),
            ).fetchone()

    def get_recording(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT recording.* FROM recordings AS recording
                JOIN families AS family ON family.id = recording.family_id
                WHERE recording.id = %s AND family.owner_user_id = %s
                """,
                (recording_id, user_id),
            ).fetchone()

    def get_recording_for_upload(self, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM recordings WHERE id = %s", (recording_id,)
            ).fetchone()

    def list_recordings(self, user_id: UUID) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT recording.* FROM recordings AS recording
                JOIN families AS family ON family.id = recording.family_id
                WHERE family.owner_user_id = %s AND recording.status <> 'DELETED'
                ORDER BY recording.created_at DESC
                """,
                (user_id,),
            ).fetchall()

    def mark_uploaded(
        self, user_id: UUID, recording_id: UUID, media_type: str, duration_ms: int,
        file_size: int, sha256: str
    ) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE recordings AS recording
                SET media_type = %s, duration_ms = %s, file_size = %s, sha256 = %s,
                    status = 'UPLOADED', error_code = NULL, updated_at = now()
                FROM families AS family
                WHERE recording.id = %s AND family.id = recording.family_id
                  AND family.owner_user_id = %s
                RETURNING recording.*
                """,
                (media_type, duration_ms, file_size, sha256, recording_id, user_id),
            ).fetchone()

    def mark_failed(self, recording_id: UUID, error_code: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE recordings SET status = 'FAILED', error_code = %s, updated_at = now()
                WHERE id = %s AND status <> 'UPLOADED'
                """,
                (error_code, recording_id),
            )

    def delete_draft(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                DELETE FROM recordings AS recording USING families AS family
                WHERE recording.id = %s AND family.id = recording.family_id
                  AND family.owner_user_id = %s
                  AND recording.status IN ('CREATED', 'UPLOADING', 'FAILED')
                RETURNING recording.*
                """,
                (recording_id, user_id),
            ).fetchone()

    def latest_recording(self, user_id: UUID) -> dict | None:
        rows = self.list_recordings(user_id)
        return rows[0] if rows else None
