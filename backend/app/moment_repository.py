from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class MomentRepository(Protocol):
    def load_source(self, recording_id: UUID) -> dict | None: ...
    def replace_moments(self, recording_id: UUID, moments: list[dict], pipeline_version: str, transcript_revision: int) -> None: ...
    def list_for_user(self, user_id: UUID, recording_id: UUID) -> list[dict] | None: ...
    def get_for_user(self, user_id: UUID, moment_id: UUID) -> dict | None: ...
    def update_for_user(self, user_id: UUID, moment_id: UUID, selection_state: str | None, start_ms: int | None, end_ms: int | None) -> dict | None: ...


class PostgresMomentRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def load_source(self, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            recording = connection.execute("SELECT * FROM recordings WHERE id = %s", (recording_id,)).fetchone()
            if recording is None:
                return None
            segments = connection.execute(
                "SELECT * FROM transcript_segments WHERE recording_id = %s ORDER BY start_ms, end_ms, id",
                (recording_id,),
            ).fetchall()
            mappings = connection.execute(
                "SELECT speaker_key, family_member_id, display_name FROM recording_speaker_mappings WHERE recording_id = %s",
                (recording_id,),
            ).fetchall()
            return {
                "recording": recording, "segments": segments,
                "speaker_names": {item["speaker_key"]: item for item in mappings},
            }

    def replace_moments(self, recording_id: UUID, moments: list[dict], pipeline_version: str, transcript_revision: int) -> None:
        with self._connect() as connection:
            recording = connection.execute(
                "SELECT family_id FROM recordings WHERE id = %s FOR UPDATE", (recording_id,)
            ).fetchone()
            if recording is None:
                raise ValueError("recording not found")
            connection.execute(
                "DELETE FROM moments WHERE recording_id = %s AND pipeline_version = %s",
                (recording_id, pipeline_version),
            )
            for item in moments:
                connection.execute(
                    """
                    INSERT INTO moments (
                      family_id, recording_id, title, theme, score, storyboard,
                      selected, pipeline_version, rank, start_ms, end_ms,
                      selection_state, score_breakdown, transcript_revision
                    ) VALUES (%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,'kept',%s,%s)
                    """,
                    (
                        recording["family_id"], recording_id, item["title"], item["theme"],
                        item["score"], Jsonb(item["storyboard"]), pipeline_version, item["rank"],
                        item["start_ms"], item["end_ms"], Jsonb(item["score_breakdown"]),
                        transcript_revision,
                    ),
                )

    @staticmethod
    def _select_sql(where: str) -> str:
        return f"""
            SELECT moment.* FROM moments AS moment
            JOIN families AS family ON family.id = moment.family_id
            WHERE {where}
        """

    def list_for_user(self, user_id: UUID, recording_id: UUID) -> list[dict] | None:
        with self._connect() as connection:
            owned = connection.execute(
                "SELECT 1 FROM recordings r JOIN families f ON f.id=r.family_id WHERE r.id=%s AND f.owner_user_id=%s",
                (recording_id, user_id),
            ).fetchone()
            if owned is None:
                return None
            return connection.execute(
                self._select_sql("moment.recording_id = %s AND family.owner_user_id = %s")
                + " ORDER BY moment.rank, moment.created_at",
                (recording_id, user_id),
            ).fetchall()

    def get_for_user(self, user_id: UUID, moment_id: UUID) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                self._select_sql("moment.id = %s AND family.owner_user_id = %s"),
                (moment_id, user_id),
            ).fetchone()

    def update_for_user(self, user_id: UUID, moment_id: UUID, selection_state: str | None, start_ms: int | None, end_ms: int | None) -> dict | None:
        with self._connect() as connection:
            moment = connection.execute(
                self._select_sql("moment.id = %s AND family.owner_user_id = %s") + " FOR UPDATE",
                (moment_id, user_id),
            ).fetchone()
            if moment is None:
                return None
            previous = {
                "selection_state": moment["selection_state"],
                "start_ms": moment["start_ms"], "end_ms": moment["end_ms"],
            }
            next_state = selection_state or moment["selection_state"]
            next_start = start_ms if start_ms is not None else moment["start_ms"]
            next_end = end_ms if end_ms is not None else moment["end_ms"]
            storyboard = dict(moment["storyboard"])
            action = next_state if selection_state else "boundary_changed"
            if start_ms is not None:
                segments = connection.execute(
                    """
                    SELECT id, speaker_key, family_member_id, start_ms, end_ms, text
                    FROM transcript_segments
                    WHERE recording_id=%s AND start_ms < %s AND end_ms > %s
                    ORDER BY start_ms, end_ms, id
                    """,
                    (moment["recording_id"], next_end, next_start),
                ).fetchall()
                if not segments:
                    return None
                storyboard["source_segments"] = [{
                    "transcript_segment_id": str(item["id"]), "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"], "quote": item["text"],
                } for item in segments]
                storyboard["setup"] = segments[0]["text"]
                storyboard["turning_point"] = segments[len(segments) // 2]["text"]
                storyboard["ending"] = segments[-1]["text"]
                storyboard["highlight_quote"] = max(segments, key=lambda item: len(item["text"]))["text"]
            updated = connection.execute(
                """
                UPDATE moments SET selection_state=%s, selected=%s, start_ms=%s, end_ms=%s,
                  storyboard=%s, edited_by_user=true, updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (next_state, next_state == "kept", next_start, next_end, Jsonb(storyboard), moment_id),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO moment_feedback (
                  family_id, recording_id, moment_id, action, previous_value, new_value
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    moment["family_id"], moment["recording_id"], moment_id, action,
                    Jsonb(previous), Jsonb({"selection_state": next_state, "start_ms": next_start, "end_ms": next_end}),
                ),
            )
            return updated
