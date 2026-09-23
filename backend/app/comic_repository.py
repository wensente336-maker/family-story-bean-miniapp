from __future__ import annotations

from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


COMPOSITE_ASSET = "/assets/comics/family-dinner-four-panel-v1.png"
PANEL_TWO_VARIANT = "/assets/comics/family-dinner-panel-2-v2.png"


class ComicRepository(Protocol):
    def create_for_moment(self, user_id: UUID, moment_id: UUID, pipeline_version: str) -> dict | None: ...
    def get_for_user(self, user_id: UUID, comic_id: UUID) -> dict | None: ...
    def regenerate_panel(self, user_id: UUID, comic_id: UUID, panel_index: int) -> dict | None: ...


class PostgresComicRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _payload(connection, creation: dict) -> dict:
        panels = connection.execute(
            "SELECT * FROM comic_panels WHERE creation_id=%s ORDER BY panel_index",
            (creation["id"],),
        ).fetchall()
        return {**creation, "panels": panels}

    @staticmethod
    def _panel_specs(storyboard: dict) -> list[dict]:
        sources = storyboard["source_segments"]
        if len(sources) == 1:
            beats = [
                f"在{storyboard['scene']}里，一家人正围坐在一起。",
                "一个意外的小插曲突然发生。",
                "大家的笑声一下子填满了房间。",
                "这个普通的家庭时刻，就这样被留了下来。",
            ]
        else:
            beats = [
                storyboard["setup"], storyboard["turning_point"],
                storyboard["ending"], "这个普通的家庭时刻，就这样被留了下来。",
            ]
        positions = [(0, 0), (1, 0), (0, 1), (1, 1)]
        specs = []
        for index, narration in enumerate(beats):
            if len(sources) == 1:
                source = sources[0] if index == 1 else None
            else:
                source = sources[min(index, len(sources) - 1)] if index < 3 else None
            dialogue = source.get("quote") if source else None
            specs.append({
                "panel_index": index + 1, "narration": narration,
                "dialogue": dialogue,
                "source_segment_id": source.get("transcript_segment_id") if source else None,
                "asset_url": COMPOSITE_ASSET, "asset_variant": "composite-v1",
                "crop_x": positions[index][0], "crop_y": positions[index][1],
                "prompt": f"{storyboard['scene']} | {narration}",
            })
        return specs

    def create_for_moment(self, user_id: UUID, moment_id: UUID, pipeline_version: str) -> dict | None:
        with self._connect() as connection:
            moment = connection.execute(
                """
                SELECT moment.* FROM moments moment
                JOIN families family ON family.id=moment.family_id
                WHERE moment.id=%s AND family.owner_user_id=%s
                  AND moment.selection_state='kept'
                FOR UPDATE
                """,
                (moment_id, user_id),
            ).fetchone()
            if moment is None:
                return None
            existing = connection.execute(
                "SELECT * FROM creations WHERE moment_id=%s AND type='COMIC' ORDER BY version DESC LIMIT 1",
                (moment_id,),
            ).fetchone()
            if existing:
                return self._payload(connection, existing)
            board = moment["storyboard"]
            visual_bible = {
                "style": "warm-editorial-family-comic",
                "palette": ["deep-teal", "coral", "mustard", "warm-cream"],
                "characters": board["characters"],
                "consistency_rule": "same face, age, hairstyle and clothing in all panels",
            }
            creation = connection.execute(
                """
                INSERT INTO creations (
                  family_id, moment_id, type, status, version, pipeline_version, title, metadata
                ) VALUES (%s,%s,'COMIC','COMPLETED',1,%s,%s,%s)
                RETURNING *
                """,
                (
                    moment["family_id"], moment_id, pipeline_version,
                    board["title"], Jsonb({"layout": "2x2", "visual_bible": visual_bible}),
                ),
            ).fetchone()
            for panel in self._panel_specs(board):
                connection.execute(
                    """
                    INSERT INTO comic_panels (
                      family_id, creation_id, panel_index, narration, dialogue,
                      source_segment_id, asset_url, asset_variant, crop_x, crop_y, prompt
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        moment["family_id"], creation["id"], panel["panel_index"],
                        panel["narration"], panel["dialogue"], panel["source_segment_id"],
                        panel["asset_url"], panel["asset_variant"], panel["crop_x"],
                        panel["crop_y"], panel["prompt"],
                    ),
                )
            return self._payload(connection, creation)

    def get_for_user(self, user_id: UUID, comic_id: UUID) -> dict | None:
        with self._connect() as connection:
            creation = connection.execute(
                """
                SELECT creation.* FROM creations creation
                JOIN families family ON family.id=creation.family_id
                WHERE creation.id=%s AND creation.type='COMIC' AND family.owner_user_id=%s
                """,
                (comic_id, user_id),
            ).fetchone()
            return self._payload(connection, creation) if creation else None

    def regenerate_panel(self, user_id: UUID, comic_id: UUID, panel_index: int) -> dict | None:
        with self._connect() as connection:
            creation = connection.execute(
                """
                SELECT creation.* FROM creations creation
                JOIN families family ON family.id=creation.family_id
                WHERE creation.id=%s AND creation.type='COMIC' AND family.owner_user_id=%s
                FOR UPDATE
                """,
                (comic_id, user_id),
            ).fetchone()
            if creation is None:
                return None
            panel = connection.execute(
                "SELECT * FROM comic_panels WHERE creation_id=%s AND panel_index=%s FOR UPDATE",
                (comic_id, panel_index),
            ).fetchone()
            if panel is None:
                return None
            next_version = panel["version"] + 1
            asset_url = PANEL_TWO_VARIANT if panel_index == 2 and next_version % 2 == 0 else COMPOSITE_ASSET
            asset_variant = f"panel-{panel_index}-v{next_version}"
            crop_x, crop_y = ((1, 0) if panel_index == 2 else (panel["crop_x"], panel["crop_y"]))
            connection.execute(
                """
                UPDATE comic_panels SET version=%s, asset_url=%s, asset_variant=%s,
                  crop_x=%s, crop_y=%s, updated_at=now()
                WHERE id=%s
                """,
                (next_version, asset_url, asset_variant, crop_x, crop_y, panel["id"]),
            )
            updated = connection.execute(
                "UPDATE creations SET version=version+1, updated_at=now() WHERE id=%s RETURNING *",
                (comic_id,),
            ).fetchone()
            return self._payload(connection, updated)
