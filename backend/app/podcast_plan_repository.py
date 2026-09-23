from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PodcastPlanRepository(Protocol):
    def get_context(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def get_plan(self, user_id: UUID, recording_id: UUID) -> dict | None: ...
    def save_plan(
        self, user_id: UUID, recording_id: UUID, plan: dict
    ) -> dict | None: ...
    def update_plan(
        self, user_id: UUID, recording_id: UUID, status: str, plan: dict
    ) -> dict | None: ...


class PostgresPodcastPlanRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _context(connection, user_id: UUID, recording_id: UUID) -> dict | None:
        row = connection.execute(
            """
            SELECT recording.id AS recording_id, recording.title AS recording_title,
                   version.id AS podcast_version_id,
                   material_set.id AS material_set_id,
                   material_set.revision AS material_revision,
                   material_set.family_id
            FROM podcast_material_sets material_set
            JOIN podcast_versions version ON version.id=material_set.podcast_version_id
            JOIN podcast_projects project ON project.id=version.project_id
            JOIN recordings recording ON recording.id=project.recording_id
            JOIN families family ON family.id=material_set.family_id
            WHERE project.recording_id=%s AND family.owner_user_id=%s
              AND project.deleted_at IS NULL
              AND material_set.status='CONFIRMED'
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
            (row["material_set_id"],),
        ).fetchall()
        return {**row, "materials": materials}

    @staticmethod
    def _payload(connection, context: dict) -> dict | None:
        row = connection.execute(
            """
            SELECT id, material_set_id, status, revision, schema_version,
                   prompt_version, model_version, plan
            FROM podcast_plans WHERE podcast_version_id=%s
            """,
            (context["podcast_version_id"],),
        ).fetchone()
        if row is None:
            return None
        plan = {
            **row["plan"],
            "id": row["id"],
            "material_set_id": row["material_set_id"],
            "status": row["status"],
            "revision": row["revision"],
            "schema_version": row["schema_version"],
            "prompt_version": row["prompt_version"] or row["plan"].get("prompt_version"),
            "model_version": row["model_version"] or row["plan"].get("model_version"),
        }
        return {
            "recording_id": context["recording_id"],
            "recording_title": context["recording_title"],
            "podcast_version_id": context["podcast_version_id"],
            "material_set_id": context["material_set_id"],
            "material_revision": context["material_revision"],
            "materials": context["materials"],
            "plan": plan,
        }

    def get_context(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            return self._context(connection, user_id, recording_id)

    def get_plan(self, user_id: UUID, recording_id: UUID) -> dict | None:
        with self._connect() as connection:
            context = self._context(connection, user_id, recording_id)
            return self._payload(connection, context) if context else None

    def save_plan(self, user_id: UUID, recording_id: UUID, plan: dict) -> dict | None:
        with self._connect() as connection:
            context = self._context(connection, user_id, recording_id)
            if context is None:
                return None
            existing = connection.execute(
                "SELECT * FROM podcast_plans WHERE podcast_version_id=%s FOR UPDATE",
                (context["podcast_version_id"],),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO podcast_plans (
                      family_id, podcast_version_id, material_set_id, status,
                      prompt_version, model_version, plan
                    ) VALUES (%s,%s,%s,'DRAFT',%s,%s,%s::jsonb)
                    """,
                    (
                        context["family_id"], context["podcast_version_id"],
                        context["material_set_id"], plan["prompt_version"],
                        plan["model_version"], Jsonb(plan),
                    ),
                )
            elif (
                existing["status"] == "DRAFT"
                and existing["plan"].get("narration_style") == plan.get("narration_style")
            ):
                return self._payload(connection, context)
            elif existing["status"] == "DRAFT":
                connection.execute(
                    """
                    UPDATE podcast_plans
                    SET plan=%s::jsonb, prompt_version=%s, model_version=%s,
                        revision=revision+1, updated_at=now()
                    WHERE id=%s
                    """,
                    (
                        Jsonb(plan), plan["prompt_version"],
                        plan["model_version"], existing["id"],
                    ),
                )
            else:
                return self._payload(connection, context)
            return self._payload(connection, context)

    def update_plan(
        self, user_id: UUID, recording_id: UUID, status: str, plan: dict
    ) -> dict | None:
        with self._connect() as connection:
            context = self._context(connection, user_id, recording_id)
            if context is None:
                return None
            existing = connection.execute(
                "SELECT * FROM podcast_plans WHERE podcast_version_id=%s FOR UPDATE",
                (context["podcast_version_id"],),
            ).fetchone()
            if existing is None:
                return None
            if existing["status"] == "CONFIRMED":
                return self._payload(connection, context) if status == "CONFIRMED" else None
            connection.execute(
                """
                UPDATE podcast_plans
                SET status=%s, plan=%s::jsonb, revision=revision+1,
                    confirmed_at=CASE WHEN %s='CONFIRMED' THEN now() ELSE NULL END,
                    updated_at=now()
                WHERE id=%s
                """,
                (status, Jsonb(plan), status, existing["id"]),
            )
            if status == "CONFIRMED":
                connection.execute(
                    """
                    UPDATE podcast_versions
                    SET status='CONFIRMED', title=%s, description=%s,
                        narrator_voice=%s, music_style=%s,
                        confirmed_at=now(), updated_at=now()
                    WHERE id=%s
                    """,
                    (
                        plan["title"], plan.get("description", ""),
                        plan["narrator_voice"], plan["music_style"],
                        context["podcast_version_id"],
                    ),
                )
            return self._payload(connection, context)
