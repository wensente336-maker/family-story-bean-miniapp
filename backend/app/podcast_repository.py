from __future__ import annotations

import hashlib
import json
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .podcast_audio import LocalPodcastRenderer, PodcastRenderError


class PodcastRepository(Protocol):
    def create(self, user_id: UUID, moment_ids: list[UUID], pipeline_version: str) -> dict | None: ...
    def get_for_user(self, user_id: UUID, podcast_id: UUID) -> dict | None: ...
    def remix(
        self, user_id: UUID, podcast_id: UUID, moment_ids: list[UUID], intro: str, outro: str
    ) -> dict | None: ...


class PostgresPodcastRepository:
    def __init__(self, database_url: str, renderer: LocalPodcastRenderer):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.renderer = renderer

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _fingerprint(moment_ids: list[UUID], intro: str, outro: str) -> str:
        value = json.dumps(
            {"moment_ids": [str(item) for item in moment_ids], "intro": intro, "outro": outro},
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _default_copy(moments: list[dict]) -> tuple[str, str, str]:
        themes = "、".join(dict.fromkeys(item.get("theme") or "日常" for item in moments))
        moment_title = moments[0]["title"].removeprefix("「").removesuffix("」的家庭时刻")
        title = f"家里的小剧场：{moment_title[:28]}"
        intro = (
            "欢迎收听《家庭故事豆》。今天我们不讲宏大的道理，"
            f"只想留住一段关于{themes}的小小回忆。"
            "这些声音来自真实的家庭时刻，笑声、停顿和偶然的小意外，"
            "都是生活本来的样子。请放慢一点，和我们一起回到那个瞬间。"
        )
        outro = (
            "这就是今天的家庭小播客。我们保留的不只是一句话，"
            "也是那天房间里的声音、大家的反应，以及只属于这个家的默契。"
            "很多年以后再听回来，也许最珍贵的，就是这些当时并没有特别注意的普通时刻。"
            "感谢收听，我们下一颗故事豆再见。"
        )
        return title, intro, outro

    @staticmethod
    def _load_moments(connection, user_id: UUID, moment_ids: list[UUID]) -> list[dict] | None:
        rows = connection.execute(
            """
            SELECT moment.*, recording.object_key AS source_object_key
            FROM moments moment
            JOIN families family ON family.id=moment.family_id
            JOIN recordings recording ON recording.id=moment.recording_id
            WHERE moment.id=ANY(%s) AND family.owner_user_id=%s
              AND moment.selection_state='kept'
            """,
            (moment_ids, user_id),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        if len(by_id) != len(moment_ids):
            return None
        ordered = [by_id[item] for item in moment_ids]
        if len({item["family_id"] for item in ordered}) != 1 or len({item["recording_id"] for item in ordered}) != 1:
            return None
        return ordered

    @staticmethod
    def _segments(moments: list[dict], intro: str, outro: str) -> list[dict]:
        segments = [{"kind": "narration", "label": "主持人开场", "text": intro}]
        for position, moment in enumerate(moments, start=1):
            board = moment["storyboard"]
            source = board["source_segments"][0]
            segments.append({
                "kind": "narration", "label": f"第 {position} 个故事",
                "text": (
                    f"第 {position} 个时刻，发生在{board['scene']}。"
                    f"{board['setup']}接着，{board['turning_point']}"
                    "我们把最真实的那句话留了下来。"
                ),
            })
            segments.append({
                "kind": "original", "label": "家人真实原声",
                "text": board["highlight_quote"], "source_moment_id": moment["id"],
                "source_segment_id": UUID(source["transcript_segment_id"]),
                "start_ms": moment["start_ms"], "end_ms": moment["end_ms"],
            })
            segments.append({
                "kind": "narration", "label": "故事回味",
                "text": (
                    f"这段声音里，有{'、'.join(board['emotion_curve'])}。"
                    f"{board['ending']}很多家庭故事并不完美，却正因如此，"
                    "我们才能在里面听见真实的彼此。"
                ),
            })
        segments.append({"kind": "narration", "label": "主持人片尾", "text": outro})
        return segments

    @staticmethod
    def _payload(connection, creation: dict) -> dict:
        moments = connection.execute(
            """
            SELECT moment.id, moment.title, moment.theme, link.position,
                   moment.start_ms, moment.end_ms
            FROM podcast_moments link JOIN moments moment ON moment.id=link.moment_id
            WHERE link.creation_id=%s ORDER BY link.position
            """,
            (creation["id"],),
        ).fetchall()
        segments = connection.execute(
            "SELECT * FROM podcast_segments WHERE creation_id=%s ORDER BY segment_index",
            (creation["id"],),
        ).fetchall()
        recording_id = connection.execute(
            "SELECT recording_id FROM moments WHERE id=%s", (creation["moment_id"],)
        ).fetchone()["recording_id"]
        return {**creation, "recording_id": recording_id, "moments": moments, "segments": segments}

    @staticmethod
    def _write_structure(connection, creation: dict, moments: list[dict], segments: list[dict]) -> None:
        connection.execute("DELETE FROM podcast_segments WHERE creation_id=%s", (creation["id"],))
        connection.execute("DELETE FROM podcast_moments WHERE creation_id=%s", (creation["id"],))
        for position, moment in enumerate(moments, start=1):
            connection.execute(
                "INSERT INTO podcast_moments (family_id,creation_id,moment_id,position) VALUES (%s,%s,%s,%s)",
                (creation["family_id"], creation["id"], moment["id"], position),
            )
        for index, segment in enumerate(segments, start=1):
            connection.execute(
                """
                INSERT INTO podcast_segments (
                  family_id,creation_id,segment_index,kind,label,text,source_moment_id,
                  source_segment_id,start_ms,end_ms
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    creation["family_id"], creation["id"], index, segment["kind"],
                    segment["label"], segment["text"], segment.get("source_moment_id"),
                    segment.get("source_segment_id"), segment.get("start_ms"), segment.get("end_ms"),
                ),
            )

    def _render_and_complete(
        self, creation: dict, moments: list[dict], segments: list[dict], fingerprint: str
    ) -> dict:
        object_key = (
            f"families/{creation['family_id']}/recordings/{moments[0]['recording_id']}"
            f"/podcasts/{creation['id']}/v{creation['version']}.mp3"
        )
        try:
            render_metadata = self.renderer.render(
                moments[0]["source_object_key"], object_key, segments
            )
            status = "COMPLETED"
            error = None
        except PodcastRenderError as exc:
            render_metadata = {"duration_ms": 0, "render_mode": "failed"}
            status = "FAILED"
            error = str(exc)
            object_key = None
        metadata = {
            **creation.get("metadata", {}), **render_metadata,
            "request_fingerprint": fingerprint, "narrator_is_ai": True,
            "original_audio_traceable": True, "error": error,
        }
        with self._connect() as connection:
            completed = connection.execute(
                """
                UPDATE creations SET status=%s, object_key=%s, metadata=%s, updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (status, object_key, Jsonb(metadata), creation["id"]),
            ).fetchone()
            return self._payload(connection, completed)

    def create(self, user_id: UUID, moment_ids: list[UUID], pipeline_version: str) -> dict | None:
        with self._connect() as connection:
            moments = self._load_moments(connection, user_id, moment_ids)
            if moments is None:
                return None
            title, intro, outro = self._default_copy(moments)
            fingerprint = self._fingerprint(moment_ids, intro, outro)
            existing = connection.execute(
                """
                SELECT creation.* FROM creations creation
                JOIN families family ON family.id=creation.family_id
                WHERE creation.moment_id=%s AND creation.type='PODCAST'
                  AND family.owner_user_id=%s ORDER BY creation.created_at DESC LIMIT 1
                """,
                (moment_ids[0], user_id),
            ).fetchone()
            if (
                existing and existing["status"] == "COMPLETED"
                and existing["metadata"].get("request_fingerprint") == fingerprint
            ):
                return self._payload(connection, existing)
            if existing:
                creation = connection.execute(
                    """
                    UPDATE creations SET status='GENERATING', version=version+1, title=%s,
                      object_key=NULL, metadata=%s, updated_at=now() WHERE id=%s RETURNING *
                    """,
                    (title, Jsonb({"intro": intro, "outro": outro}), existing["id"]),
                ).fetchone()
            else:
                creation = connection.execute(
                    """
                    INSERT INTO creations (
                      family_id,moment_id,type,status,version,pipeline_version,title,metadata
                    ) VALUES (%s,%s,'PODCAST','GENERATING',1,%s,%s,%s) RETURNING *
                    """,
                    (
                        moments[0]["family_id"], moments[0]["id"], pipeline_version,
                        title, Jsonb({"intro": intro, "outro": outro}),
                    ),
                ).fetchone()
            segments = self._segments(moments, intro, outro)
            self._write_structure(connection, creation, moments, segments)
        return self._render_and_complete(creation, moments, segments, fingerprint)

    def get_for_user(self, user_id: UUID, podcast_id: UUID) -> dict | None:
        with self._connect() as connection:
            creation = connection.execute(
                """
                SELECT creation.* FROM creations creation
                JOIN families family ON family.id=creation.family_id
                WHERE creation.id=%s AND creation.type='PODCAST' AND family.owner_user_id=%s
                """,
                (podcast_id, user_id),
            ).fetchone()
            return self._payload(connection, creation) if creation else None

    def remix(
        self, user_id: UUID, podcast_id: UUID, moment_ids: list[UUID], intro: str, outro: str
    ) -> dict | None:
        with self._connect() as connection:
            creation = connection.execute(
                """
                SELECT creation.* FROM creations creation
                JOIN families family ON family.id=creation.family_id
                WHERE creation.id=%s AND creation.type='PODCAST' AND family.owner_user_id=%s
                FOR UPDATE
                """,
                (podcast_id, user_id),
            ).fetchone()
            moments = self._load_moments(connection, user_id, moment_ids)
            if creation is None or moments is None:
                return None
            fingerprint = self._fingerprint(moment_ids, intro, outro)
            if (
                creation["status"] == "COMPLETED"
                and creation["metadata"].get("request_fingerprint") == fingerprint
            ):
                return self._payload(connection, creation)
            creation = connection.execute(
                """
                UPDATE creations SET status='GENERATING', version=version+1,
                  object_key=NULL, metadata=%s, updated_at=now() WHERE id=%s RETURNING *
                """,
                (Jsonb({"intro": intro, "outro": outro}), podcast_id),
            ).fetchone()
            segments = self._segments(moments, intro, outro)
            self._write_structure(connection, creation, moments, segments)
        return self._render_and_complete(creation, moments, segments, fingerprint)
