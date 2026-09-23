from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class TranscriptRepository(Protocol):
    def replace_transcript(self, recording_id: UUID, result: dict, pipeline_version: str) -> None: ...
    def get_for_user(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def update_segment(
        self, user_id: UUID, recording_id: UUID, segment_id: UUID,
        text: str | None, speaker_key: str | None,
    ) -> dict | None: ...
    def set_speaker_mapping(
        self, user_id: UUID, recording_id: UUID, speaker_key: str,
        family_member_id: UUID | None, display_name: str,
    ) -> dict | None: ...


class PostgresTranscriptRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def get_recording_internal(self, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT recording.*,
                  COALESCE(
                    array_agg(member.nickname ORDER BY member.created_at, member.id)
                      FILTER (WHERE member.id IS NOT NULL),
                    ARRAY[]::text[]
                  ) AS family_member_names
                FROM recordings recording
                LEFT JOIN family_members member ON member.family_id = recording.family_id
                WHERE recording.id = %s
                GROUP BY recording.id
                """,
                (recording_id,),
            ).fetchone()

    def replace_transcript(self, recording_id: UUID, result: dict, pipeline_version: str) -> None:
        with self._connect() as connection:
            recording = connection.execute(
                "SELECT id, family_id FROM recordings WHERE id = %s FOR UPDATE",
                (recording_id,),
            ).fetchone()
            if recording is None:
                raise ValueError("recording not found")
            connection.execute(
                "DELETE FROM transcript_segments WHERE recording_id = %s", (recording_id,)
            )
            connection.execute(
                "DELETE FROM recording_speaker_mappings WHERE recording_id = %s",
                (recording_id,),
            )
            speakers = sorted({segment["speaker_key"] for segment in result["segments"]})
            for speaker_key in speakers:
                display_name = speaker_key.replace("speaker_", "说话人 ").upper()
                connection.execute(
                    """
                    INSERT INTO recording_speaker_mappings (
                      family_id, recording_id, speaker_key, display_name
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (recording["family_id"], recording_id, speaker_key, display_name),
                )
            for segment in result["segments"]:
                connection.execute(
                    """
                    INSERT INTO transcript_segments (
                      family_id, recording_id, speaker_key, start_ms, end_ms,
                      text, original_text, confidence, words, edited_by_user,
                      pipeline_version
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s)
                    """,
                    (
                        recording["family_id"], recording_id, segment["speaker_key"],
                        segment["start_ms"], segment["end_ms"], segment["text"],
                        segment["text"], segment.get("confidence"),
                        Jsonb(segment.get("words", [])), pipeline_version,
                    ),
                )
            connection.execute(
                """
                UPDATE recordings SET transcript_language = %s, asr_provider = %s,
                  asr_model = %s, transcript_revision = transcript_revision + 1,
                  updated_at = now()
                WHERE id = %s
                """,
                (
                    result.get("language"), result.get("provider"),
                    result.get("model"), recording_id,
                ),
            )

    def get_for_user(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            recording = connection.execute(
                """
                SELECT recording.* FROM recordings AS recording
                JOIN families AS family ON family.id = recording.family_id
                WHERE recording.id = %s AND family.owner_user_id = %s
                """,
                (recording_id, user_id),
            ).fetchone()
            if recording is None:
                return None
            segments = connection.execute(
                """
                SELECT id, recording_id, family_member_id, speaker_key, start_ms,
                  end_ms, text, original_text, confidence, words, edited_by_user,
                  pipeline_version, created_at, updated_at
                FROM transcript_segments WHERE recording_id = %s
                ORDER BY start_ms, end_ms, id
                """,
                (recording_id,),
            ).fetchall()
            speakers = connection.execute(
                """
                SELECT speaker_key, family_member_id, display_name
                FROM recording_speaker_mappings WHERE recording_id = %s
                ORDER BY speaker_key
                """,
                (recording_id,),
            ).fetchall()
            members = connection.execute(
                "SELECT id, nickname FROM family_members WHERE family_id = %s ORDER BY created_at, id",
                (recording["family_id"],),
            ).fetchall()
            return {"recording": recording, "segments": segments, "speakers": speakers, "members": members}

    def update_segment(
        self, user_id: UUID, recording_id: UUID, segment_id: UUID,
        text: str | None, speaker_key: str | None,
    ) -> dict | None:
        assignments = []
        values: list = []
        if text is not None:
            assignments.extend(["text = %s", "edited_by_user = true"])
            values.append(text.strip())
        if speaker_key is not None:
            assignments.extend(["speaker_key = %s", "family_member_id = %s"])
        assignments.append("updated_at = now()")
        with self._connect() as connection:
            allowed = connection.execute(
                """
                SELECT recording.family_id FROM recordings AS recording
                JOIN families AS family ON family.id = recording.family_id
                WHERE recording.id = %s AND family.owner_user_id = %s
                """,
                (recording_id, user_id),
            ).fetchone()
            if allowed is None:
                return None
            if speaker_key is not None:
                target_mapping = connection.execute(
                    """
                    INSERT INTO recording_speaker_mappings (
                      family_id, recording_id, speaker_key, display_name
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (recording_id, speaker_key) DO UPDATE
                    SET speaker_key = EXCLUDED.speaker_key
                    RETURNING family_member_id
                    """,
                    (
                        allowed["family_id"], recording_id, speaker_key,
                        speaker_key.replace("speaker_", "说话人 ").upper(),
                    ),
                ).fetchone()
                values.extend([speaker_key, target_mapping["family_member_id"]])
            values.extend([segment_id, recording_id])
            segment = connection.execute(
                f"""
                UPDATE transcript_segments SET {', '.join(assignments)}
                WHERE id = %s AND recording_id = %s
                RETURNING id, recording_id, family_member_id, speaker_key, start_ms,
                  end_ms, text, original_text, confidence, words, edited_by_user,
                  pipeline_version, created_at, updated_at
                """,
                values,
            ).fetchone()
            if segment:
                connection.execute(
                    "UPDATE recordings SET transcript_revision = transcript_revision + 1, updated_at = now() WHERE id = %s",
                    (recording_id,),
                )
            return segment

    def set_speaker_mapping(
        self, user_id: UUID, recording_id: UUID, speaker_key: str,
        family_member_id: UUID | None, display_name: str,
    ) -> dict | None:
        with self._connect() as connection:
            recording = connection.execute(
                """
                SELECT recording.family_id FROM recordings AS recording
                JOIN families AS family ON family.id = recording.family_id
                WHERE recording.id = %s AND family.owner_user_id = %s
                """,
                (recording_id, user_id),
            ).fetchone()
            if recording is None:
                return None
            if family_member_id is not None:
                member = connection.execute(
                    "SELECT nickname FROM family_members WHERE id = %s AND family_id = %s",
                    (family_member_id, recording["family_id"]),
                ).fetchone()
                if member is None:
                    return None
                display_name = member["nickname"]
            mapping = connection.execute(
                """
                INSERT INTO recording_speaker_mappings (
                  family_id, recording_id, speaker_key, family_member_id, display_name
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (recording_id, speaker_key) DO UPDATE
                SET family_member_id = EXCLUDED.family_member_id,
                    display_name = EXCLUDED.display_name, updated_at = now()
                RETURNING speaker_key, family_member_id, display_name
                """,
                (
                    recording["family_id"], recording_id, speaker_key,
                    family_member_id, display_name.strip(),
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE transcript_segments SET family_member_id = %s, updated_at = now()
                WHERE recording_id = %s AND speaker_key = %s
                """,
                (family_member_id, recording_id, speaker_key),
            )
            connection.execute(
                "UPDATE recordings SET transcript_revision = transcript_revision + 1, updated_at = now() WHERE id = %s",
                (recording_id,),
            )
            return mapping
