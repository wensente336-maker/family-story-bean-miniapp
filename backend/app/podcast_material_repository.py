from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class PodcastMaterialRepository(Protocol):
    def get_for_user(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def get_or_create_draft(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def update(
        self, user_id: UUID, recording_id: UUID, status: str, materials: list[dict]
    ) -> dict | None: ...


class PostgresPodcastMaterialRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def highlight_source_segment_id(board: dict) -> str | None:
        source_items = board.get("source_segments") or []
        highlight = str(board.get("highlight_quote") or "").strip()
        matched_source = next(
            (
                item for item in source_items
                if str(item.get("quote") or "").strip() == highlight
            ),
            None,
        )
        if matched_source is None and highlight:
            matched_source = next(
                (
                    item for item in source_items
                    if highlight in str(item.get("quote") or "")
                    or str(item.get("quote") or "").strip() in highlight
                ),
                None,
            )
        source = matched_source or (source_items[0] if source_items else {})
        return source.get("transcript_segment_id")

    @staticmethod
    def _recording(connection, user_id: UUID, recording_id: UUID) -> dict | None:
        return connection.execute(
            """
            SELECT recording.*, family.owner_user_id
            FROM recordings recording
            JOIN families family ON family.id=recording.family_id
            WHERE recording.id=%s AND family.owner_user_id=%s
            """,
            (recording_id, user_id),
        ).fetchone()

    @staticmethod
    def _payload(connection, user_id: UUID, recording_id: UUID) -> dict | None:
        row = connection.execute(
            """
            SELECT material_set.id, material_set.recording_id, material_set.status,
                   material_set.revision, material_set.schema_version,
                   material_set.transcript_revision, material_set.created_at,
                   material_set.updated_at, version.id AS podcast_version_id,
                   version.project_id, recording.title AS recording_title,
                   recording.duration_ms AS recording_duration_ms
            FROM podcast_material_sets material_set
            JOIN podcast_versions version ON version.id=material_set.podcast_version_id
            JOIN podcast_projects project ON project.id=version.project_id
            JOIN recordings recording ON recording.id=material_set.recording_id
            JOIN families family ON family.id=material_set.family_id
            WHERE project.recording_id=%s AND family.owner_user_id=%s
              AND project.deleted_at IS NULL
            ORDER BY version.version DESC LIMIT 1
            """,
            (recording_id, user_id),
        ).fetchone()
        if row is None:
            return None
        materials = connection.execute(
            """
            SELECT id, source_moment_id, source_recording_id, source_segment_id,
                   family_member_id, speaker_key, speaker_label, role, position,
                   start_ms, end_ms, original_text, confirmed_text, share_allowed
            FROM podcast_materials WHERE material_set_id=%s ORDER BY position
            """,
            (row["id"],),
        ).fetchall()
        members = connection.execute(
            """
            SELECT id, nickname FROM family_members
            WHERE family_id=(SELECT family_id FROM recordings WHERE id=%s)
            ORDER BY created_at, id
            """,
            (recording_id,),
        ).fetchall()
        return {**row, "materials": materials, "family_members": members}

    @staticmethod
    def _initial_materials(connection, recording_id: UUID) -> list[dict]:
        moments = connection.execute(
            """
            SELECT id, family_id, recording_id, rank, start_ms, end_ms, storyboard
            FROM moments
            WHERE recording_id=%s AND selection_state='kept'
              AND start_ms IS NOT NULL AND end_ms IS NOT NULL
            ORDER BY rank NULLS LAST, score DESC, created_at
            LIMIT 10
            """,
            (recording_id,),
        ).fetchall()
        materials = []
        count = len(moments)
        for index, moment in enumerate(moments, start=1):
            board = moment["storyboard"] or {}
            highlight = str(board.get("highlight_quote") or "").strip()
            source_id = PostgresPodcastMaterialRepository.highlight_source_segment_id(board)
            segment = None
            if source_id:
                segment = connection.execute(
                    """
                    SELECT segment.*, mapping.display_name
                    FROM transcript_segments segment
                    LEFT JOIN recording_speaker_mappings mapping
                      ON mapping.recording_id=segment.recording_id
                     AND mapping.speaker_key=segment.speaker_key
                    WHERE segment.id=%s AND segment.recording_id=%s
                    """,
                    (source_id, recording_id),
                ).fetchone()
            if segment is None:
                segment = connection.execute(
                    """
                    SELECT segment.*, mapping.display_name
                    FROM transcript_segments segment
                    LEFT JOIN recording_speaker_mappings mapping
                      ON mapping.recording_id=segment.recording_id
                     AND mapping.speaker_key=segment.speaker_key
                    WHERE segment.recording_id=%s
                      AND segment.start_ms < %s AND segment.end_ms > %s
                    ORDER BY LEAST(segment.end_ms, %s) - GREATEST(segment.start_ms, %s) DESC
                    LIMIT 1
                    """,
                    (
                        recording_id, moment["end_ms"], moment["start_ms"],
                        moment["end_ms"], moment["start_ms"],
                    ),
                ).fetchone()
            if segment is None:
                continue
            if count == 1:
                role = "highlight"
            elif index == 1:
                role = "setup"
            elif index == count:
                role = "ending"
            else:
                role = "highlight"
            materials.append({
                "source_moment_id": moment["id"],
                "source_recording_id": recording_id,
                "source_segment_id": segment["id"],
                "family_member_id": segment["family_member_id"],
                "speaker_key": segment["speaker_key"],
                "speaker_label": segment.get("display_name") or segment["speaker_key"],
                "role": role,
                "position": len(materials) + 1,
                "start_ms": moment["start_ms"],
                "end_ms": moment["end_ms"],
                "original_text": segment["original_text"],
                "confirmed_text": highlight or segment["text"],
                "share_allowed": True,
            })
        return materials

    def get_for_user(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return self._payload(connection, user_id, recording_id)

    def get_or_create_draft(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            recording = self._recording(connection, user_id, recording_id)
            if recording is None:
                return None
            project = connection.execute(
                "SELECT * FROM podcast_projects WHERE recording_id=%s FOR UPDATE",
                (recording_id,),
            ).fetchone()
            if project and project.get("deleted_at"):
                return None
            if project is None:
                project = connection.execute(
                    """
                    INSERT INTO podcast_projects (
                      family_id, recording_id, created_by_user_id, title
                    ) VALUES (%s,%s,%s,%s) RETURNING *
                    """,
                    (recording["family_id"], recording_id, user_id, recording["title"]),
                ).fetchone()
            current = connection.execute(
                """
                SELECT version.*, material_set.id AS material_set_id,
                       material_set.status AS material_status
                FROM podcast_versions version
                LEFT JOIN podcast_material_sets material_set
                  ON material_set.podcast_version_id=version.id
                WHERE version.project_id=%s ORDER BY version.version DESC LIMIT 1
                """,
                (project["id"],),
            ).fetchone()
            if current and current.get("material_status") == "DRAFT":
                return self._payload(connection, user_id, recording_id)

            next_version = 1 if current is None else current["version"] + 1
            version = connection.execute(
                """
                INSERT INTO podcast_versions (
                  family_id, project_id, version, status, title
                ) VALUES (%s,%s,%s,'DRAFT',%s) RETURNING *
                """,
                (
                    recording["family_id"], project["id"], next_version,
                    current["title"] if current else recording["title"],
                ),
            ).fetchone()
            material_set = connection.execute(
                """
                INSERT INTO podcast_material_sets (
                  family_id, podcast_version_id, recording_id, status,
                  transcript_revision
                ) VALUES (%s,%s,%s,'DRAFT',%s) RETURNING *
                """,
                (
                    recording["family_id"], version["id"], recording_id,
                    recording.get("transcript_revision") or 0,
                ),
            ).fetchone()

            if current and current.get("material_set_id"):
                source_materials = self._initial_materials(connection, recording_id)
            else:
                source_materials = []
            if not source_materials and current and current.get("material_set_id"):
                source_materials = connection.execute(
                    """
                    SELECT source_moment_id, source_recording_id, source_segment_id,
                           family_member_id, speaker_key, speaker_label, role, position,
                           start_ms, end_ms, original_text, confirmed_text, share_allowed
                    FROM podcast_materials WHERE material_set_id=%s ORDER BY position
                    """,
                    (current["material_set_id"],),
                ).fetchall()
            if not source_materials:
                source_materials = self._initial_materials(connection, recording_id)
            if not source_materials:
                connection.execute("DELETE FROM podcast_versions WHERE id=%s", (version["id"],))
                if current is None:
                    connection.execute("DELETE FROM podcast_projects WHERE id=%s", (project["id"],))
                return None
            for item in source_materials:
                connection.execute(
                    """
                    INSERT INTO podcast_materials (
                      family_id, material_set_id, source_moment_id, source_recording_id,
                      source_segment_id, family_member_id, speaker_key, speaker_label,
                      role, position, start_ms, end_ms, original_text, confirmed_text,
                      share_allowed
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        recording["family_id"], material_set["id"],
                        item.get("source_moment_id"), item["source_recording_id"],
                        item["source_segment_id"], item.get("family_member_id"),
                        item["speaker_key"], item["speaker_label"], item["role"],
                        item["position"], item["start_ms"], item["end_ms"],
                        item["original_text"], item["confirmed_text"],
                        item.get("share_allowed", True),
                    ),
                )
            connection.execute(
                "UPDATE podcast_projects SET current_version=%s, updated_at=now() WHERE id=%s",
                (next_version, project["id"]),
            )
            return self._payload(connection, user_id, recording_id)

    def update(
        self, user_id: UUID, recording_id: UUID, status: str, materials: list[dict]
    ) -> dict | None:
        with self._connect() as connection:
            recording = self._recording(connection, user_id, recording_id)
            if recording is None:
                return None
            material_set = connection.execute(
                """
                SELECT material_set.*, version.id AS version_id
                FROM podcast_material_sets material_set
                JOIN podcast_versions version ON version.id=material_set.podcast_version_id
                JOIN podcast_projects project ON project.id=version.project_id
                WHERE project.recording_id=%s AND material_set.status='DRAFT'
                ORDER BY version.version DESC LIMIT 1 FOR UPDATE OF material_set
                """,
                (recording_id,),
            ).fetchone()
            if material_set is None:
                return None
            existing = connection.execute(
                "SELECT * FROM podcast_materials WHERE material_set_id=%s",
                (material_set["id"],),
            ).fetchall()
            existing_by_id = {item["id"]: item for item in existing}
            requested_ids = {item["id"] for item in materials}
            if not requested_ids.issubset(existing_by_id):
                return None
            for item in materials:
                if item["end_ms"] > recording["duration_ms"]:
                    raise ValueError("material range exceeds recording duration")
                current = existing_by_id[item["id"]]
                member_id = item.get("family_member_id")
                speaker_label = item["speaker_label"].strip()
                if member_id is not None:
                    member = connection.execute(
                        "SELECT nickname FROM family_members WHERE id=%s AND family_id=%s",
                        (member_id, recording["family_id"]),
                    ).fetchone()
                    if member is None:
                        return None
                    speaker_label = member["nickname"]
                    connection.execute(
                        """
                        UPDATE transcript_segments SET family_member_id=%s, updated_at=now()
                        WHERE recording_id=%s AND speaker_key=%s
                        """,
                        (member_id, recording_id, current["speaker_key"]),
                    )
                    connection.execute(
                        """
                        UPDATE recording_speaker_mappings
                        SET family_member_id=%s, display_name=%s, updated_at=now()
                        WHERE recording_id=%s AND speaker_key=%s
                        """,
                        (member_id, speaker_label, recording_id, current["speaker_key"]),
                    )
                connection.execute(
                    """
                    UPDATE podcast_materials
                    SET family_member_id=%s, speaker_label=%s, role=%s, position=%s,
                        start_ms=%s, end_ms=%s, confirmed_text=%s,
                        share_allowed=%s, updated_at=now()
                    WHERE id=%s AND material_set_id=%s
                    """,
                    (
                        member_id, speaker_label, item["role"], item["position"],
                        item["start_ms"], item["end_ms"],
                        item["confirmed_text"].strip(), item["share_allowed"],
                        item["id"], material_set["id"],
                    ),
                )
            remove_ids = set(existing_by_id) - requested_ids
            if remove_ids:
                connection.execute(
                    "DELETE FROM podcast_materials WHERE material_set_id=%s AND id=ANY(%s)",
                    (material_set["id"], list(remove_ids)),
                )
            connection.execute(
                """
                UPDATE podcast_material_sets
                SET status=%s, revision=revision+1, transcript_revision=%s,
                    confirmed_by_user_id=%s, confirmed_at=CASE WHEN %s='CONFIRMED'
                      THEN now() ELSE NULL END, updated_at=now()
                WHERE id=%s
                """,
                (
                    status, recording.get("transcript_revision") or 0,
                    user_id if status == "CONFIRMED" else None, status,
                    material_set["id"],
                ),
            )
            connection.execute(
                """
                UPDATE podcast_versions SET status=%s,
                  confirmed_at=CASE WHEN %s='CONFIRMED' THEN now() ELSE NULL END,
                  updated_at=now() WHERE id=%s
                """,
                (status, status, material_set["version_id"]),
            )
            return self._payload(connection, user_id, recording_id)
