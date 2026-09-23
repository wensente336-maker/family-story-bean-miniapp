from __future__ import annotations

from uuid import UUID


SOURCE_SCHEMA_VERSION = "sound-story-source-v1"
DIRECTOR_SCHEMA_VERSION = "sound-story-director-v1"

TOMATO_SCENE_ASSETS = [
    "/assets/storybooks/tomato-v1/scene-01-cover.webp",
    "/assets/storybooks/tomato-v1/scene-02-setup.webp",
    "/assets/storybooks/tomato-v1/scene-03-action.webp",
    "/assets/storybooks/tomato-v1/scene-04-miaomiao.webp",
    "/assets/storybooks/tomato-v1/scene-05-laughter.webp",
    "/assets/storybooks/tomato-v1/scene-06-father.webp",
    "/assets/storybooks/tomato-v1/scene-07-ending.webp",
]


class SoundStoryDirector:
    """Turns user-approved transcript facts into one audiovisual directing script."""

    @staticmethod
    def _source_clips(context: dict, selections: dict[str, bool] | None = None) -> list[dict]:
        selections = selections or {}
        segments = context.get("transcript_segments") or []
        if not segments:
            segments = [{
                "id": item["transcript_segment_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "text": item.get("quote") or "",
                "speaker_key": "speaker",
                "speaker_name": "家人",
            } for item in (context.get("storyboard") or {}).get("source_segments", [])]
        return [{
            "source_segment_id": str(item["id"]),
            "speaker_key": item.get("speaker_key") or "speaker",
            "speaker_name": item.get("speaker_name") or item.get("speaker_key") or "家人",
            "start_ms": item["start_ms"],
            "end_ms": item["end_ms"],
            "text": item["text"],
            "included": selections.get(str(item["id"]), True),
            "locked": True,
            "role": "original",
        } for item in segments]

    @staticmethod
    def _audio_item(kind: str, text: str, clip: dict | None = None) -> dict:
        item = {"kind": kind, "text": text}
        if clip:
            item.update({
                "source_segment_id": clip["source_segment_id"],
                "speaker_name": clip["speaker_name"],
                "start_ms": clip["start_ms"],
                "end_ms": clip["end_ms"],
            })
        return item

    @staticmethod
    def _scene(
        index: int, kind: str, title: str, purpose: str, narration: str,
        visual: str, panel_index: int, clip: dict | None = None,
        asset_url: str | None = None,
    ) -> dict:
        audio_sequence = []
        if narration:
            audio_sequence.append(SoundStoryDirector._audio_item("narration", narration))
        if clip:
            audio_sequence.append(SoundStoryDirector._audio_item("original", clip["text"], clip))
        return {
            "scene_index": index,
            "page_index": index,
            "type": "cover" if index == 0 else "story",
            "scene_kind": kind,
            "story_purpose": purpose,
            "title": title,
            "narration": narration,
            "quote": clip["text"] if clip else None,
            "source_segment_id": clip["source_segment_id"] if clip else None,
            "speaker_name": clip["speaker_name"] if clip else None,
            "visual_description": visual,
            "image_prompt": (
                f"温暖电影感家庭漫画，{visual}。同一本绘本中人物脸型、年龄、发型、服装一致；"
                "画面真实自然，不在图像中生成文字。"
            ),
            "asset_url": asset_url,
            "fallback_panel_index": panel_index,
            "audio_sequence": audio_sequence,
            "traceability": {
                "mode": "original" if clip else "creative-narration",
                "source_segment_ids": [clip["source_segment_id"]] if clip else [],
            },
        }

    def compose(
        self, context: dict, selections: dict[str, bool] | None = None,
        narration_style: str = "温暖克制",
    ) -> dict:
        clips = self._source_clips(context, selections)
        included = [clip for clip in clips if clip["included"]]
        title = context.get("title") or context["manifest"]["title"]
        tomato_story = "西红柿" in title or any("西红柿" in clip["text"] for clip in included)

        source_story = {
            "schema_version": SOURCE_SCHEMA_VERSION,
            "source_recording_id": str(context["source_recording_id"]),
            "title": title,
            "priority": ["original_voice", "room_sound", "narration", "music"],
            "narration_style": narration_style,
            "clips": clips,
        }

        scenes: list[dict] = []
        if tomato_story:
            scenes.append(self._scene(
                0, "cover", title, "建立故事期待",
                "那天的晚饭，本来和往常一样。",
                "夜晚暖光下，一家人围坐餐桌，饭菜冒着热气，气氛平静自然",
                1, asset_url=TOMATO_SCENE_ASSETS[0],
            ))
            scenes.append(self._scene(
                1, "setup", "平静的晚饭", "交代人物与环境",
                "一家人围坐在桌边，谁也没想到，一颗西红柿会成为今晚的主角。",
                "餐桌全景，孩子期待地看着爸爸夹菜，妈妈在一旁微笑",
                1, asset_url=TOMATO_SCENE_ASSETS[1],
            ))
            scenes.append(self._scene(
                2, "action", "西红柿飞了起来", "触发故事事件",
                "爸爸手里的西红柿突然滑了出去，越过餐桌，落进了汤里。",
                "动作瞬间，西红柿从爸爸筷子间飞出，孩子睁大眼睛，全家视线追随",
                2, asset_url=TOMATO_SCENE_ASSETS[2],
            ))
            if included:
                scenes.append(self._scene(
                    3, "dialogue", "苗苗听见了西红柿", "用人物原声完成第一次转折",
                    "", "孩子盯着汤里的西红柿，认真又天真地替它说话，其他家人看向她",
                    1, included[0], TOMATO_SCENE_ASSETS[3],
                ))
            if len(included) > 1:
                scenes.append(self._scene(
                    4, "reaction", "笑声填满餐桌", "保留真实笑声与家庭反应",
                    "", "妈妈忍不住笑起来，爸爸有点尴尬，孩子也跟着笑，捕捉自然反应",
                    3, included[1], TOMATO_SCENE_ASSETS[4],
                ))
            if len(included) > 2:
                scenes.append(self._scene(
                    5, "dialogue", "冠军事故现场", "用回应完成喜剧落点",
                    "", "爸爸拿起抹布，一本正经地接受任务，家人仍带着笑意",
                    2, included[2], TOMATO_SCENE_ASSETS[5],
                ))
            scenes.append(self._scene(
                len(scenes), "ending", "今天最好记的事", "情绪收束",
                "一颗西红柿没有飞到奶奶家，却把全家的笑声留在了这顿晚饭里。",
                "一家人一起收拾桌面，仍然笑着，暖光包围餐桌，像一张家庭纪念照",
                4, asset_url=TOMATO_SCENE_ASSETS[6],
            ))
        else:
            scene_name = (context.get("storyboard") or {}).get("scene") or "家里的日常"
            scenes.append(self._scene(
                0, "cover", title, "建立故事期待",
                f"这是发生在{scene_name}的一段家庭故事。",
                f"{scene_name}的温暖全景，家人自然相处",
                1,
            ))
            for index, clip in enumerate(included, start=1):
                scenes.append(self._scene(
                    index, "dialogue", f"第 {index} 个家庭时刻", "让人物原声推动故事",
                    "", f"{clip['speaker_name']}说出这句话时的动作、表情，以及其他家人的即时反应",
                    ((index - 1) % 4) + 1, clip,
                ))
            scenes.append(self._scene(
                len(scenes), "ending", "把这一刻留给未来", "情绪收束",
                "真正值得保存的，往往就是这些当时看起来很普通的时刻。",
                "家人在同一空间自然相处的温暖收尾画面",
                4,
            ))

        scenes[-1]["type"] = "ending"
        director_script = {
            "schema_version": DIRECTOR_SCHEMA_VERSION,
            "title": title,
            "creative_rule": "sound-first",
            "master_clock": "audio-timeline",
            "scene_count": len(scenes),
            "scenes": scenes,
        }
        return {"source_story": source_story, "director_script": director_script}


def selection_map(items: list[dict]) -> dict[str, bool]:
    return {str(item["source_segment_id"]): bool(item["included"]) for item in items}


def uuid_or_none(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(value)
