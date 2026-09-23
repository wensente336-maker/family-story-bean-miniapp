from __future__ import annotations

from .config import Settings
from .podcast_audio import LocalPodcastRenderer, PodcastRenderError


class StorybookExperienceError(RuntimeError):
    pass


class StorybookStorylineComposer:
    """Builds one guarded story spine from transcript-backed quotes and comic pages."""

    @staticmethod
    def _quote_map(storyboard: dict) -> dict[str, str]:
        return {
            str(item["transcript_segment_id"]): item["quote"]
            for item in storyboard.get("source_segments", [])
            if item.get("transcript_segment_id") and item.get("quote")
        }

    def compose(self, context: dict) -> dict:
        story_plan = context.get("story_plan")
        if story_plan:
            director = story_plan["director_script"]
            return {
                "schema_version": "sound-storyline-v2",
                "title": director["title"],
                "source": "user-confirmed-sound-story",
                "story_plan_revision": story_plan["revision"],
                "scenes": [dict(scene) for scene in director["scenes"]],
            }
        manifest = context["manifest"]
        storyboard = context.get("storyboard") or {}
        quote_map = self._quote_map(storyboard)
        title = manifest["title"]
        tomato_story = "西红柿" in title or any("西红柿" in text for text in quote_map.values())
        story_pages = [page for page in manifest["pages"] if page["type"] == "story"]

        if tomato_story:
            bridges = [
                "晚饭本来照常进行，直到爸爸手里的西红柿滑了出去。苗苗盯着它，认真替它说出了心声。",
                "西红柿落进汤里，餐桌安静了半秒。下一秒，妈妈先笑出了声。",
                "爸爸看着眼前的冠军事故现场，也一本正经地接过了话。",
                "一颗西红柿没有飞到奶奶家，却把全家的笑声留在了这顿晚饭里。",
            ]
            cover_narration = "晚饭桌上，一颗西红柿突然飞了起来。故事，就从这一刻开始。"
            ending_narration = "很多年以后，他们或许忘了那天吃了什么，但一定还会记得这颗会飞的西红柿。"
        else:
            scene = storyboard.get("scene") or "家里的日常"
            bridges = [
                f"那天在{scene}，一个平常的时刻悄悄变成了故事。",
                "紧接着，家人的反应让故事有了意想不到的转折。",
                "笑声还没有停，又有人接过了话。",
                storyboard.get("ending") or "这个普通的瞬间，就这样被一家人记了下来。",
            ]
            cover_narration = f"这是关于{title}的家庭故事。让我们回到它发生的那一刻。"
            ending_narration = "真正值得保存的，往往就是这些当时看起来很普通的时刻。"

        scenes = [{
            "page_index": 0,
            "type": "cover",
            "title": title,
            "narration": cover_narration,
            "quote": None,
            "source_segment_id": None,
            "image_prompt": f"家庭绘本封面，主题为《{title}》，温暖真实、人物一致",
        }]
        for position, page in enumerate(story_pages):
            clip = page.get("clip")
            source_segment_id = str(clip["source_segment_id"]) if clip else None
            quote = quote_map.get(source_segment_id or "")
            narration = bridges[position] if position < len(bridges) else page["narration"]
            scenes.append({
                "page_index": page["index"],
                "type": "story",
                "title": page["title"],
                "narration": narration,
                "quote": quote,
                "source_segment_id": source_segment_id,
                "image_prompt": (
                    f"连贯家庭绘本第{position + 1}幕：{narration}"
                    "；保持同一家庭成员的脸型、年龄、发型与服装一致"
                ),
            })
        ending_page = manifest["pages"][-1]
        scenes.append({
            "page_index": ending_page["index"],
            "type": "ending",
            "title": ending_page["title"],
            "narration": ending_narration,
            "quote": None,
            "source_segment_id": None,
            "image_prompt": f"家庭绘本封底，延续《{title}》的温暖灯光与人物设定",
        })
        return {
            "schema_version": "storybook-storyline-v1",
            "title": title,
            "source": "transcript-grounded",
            "scenes": scenes,
        }

    @staticmethod
    def audio_segments(storyline: dict, manifest: dict) -> list[dict]:
        page_map = {page["index"]: page for page in manifest["pages"]}
        segments = []
        for scene in storyline["scenes"]:
            if scene.get("audio_sequence") is not None:
                for item in scene["audio_sequence"]:
                    segment = {
                        "kind": item["kind"],
                        "label": "家人真实原声" if item["kind"] == "original" else "故事解说",
                        "text": item["text"],
                        "page_index": scene["page_index"],
                    }
                    if item["kind"] == "original":
                        segment.update({
                            "source_segment_id": item["source_segment_id"],
                            "start_ms": item["start_ms"],
                            "end_ms": item["end_ms"],
                        })
                    segments.append(segment)
                continue
            segments.append({
                "kind": "narration",
                "label": "故事解说",
                "text": scene["narration"],
                "page_index": scene["page_index"],
            })
            page = page_map.get(scene["page_index"], {})
            clip = page.get("clip")
            if clip and scene.get("quote"):
                segments.append({
                    "kind": "original",
                    "label": "家人真实原声",
                    "text": scene["quote"],
                    "page_index": scene["page_index"],
                    "source_segment_id": clip["source_segment_id"],
                    "start_ms": clip["start_ms"],
                    "end_ms": clip["end_ms"],
                })
        return segments


class StorybookExperienceRenderer:
    def __init__(self, settings: Settings):
        self.renderer = LocalPodcastRenderer(settings)
        self.composer = StorybookStorylineComposer()

    def render(self, context: dict, destination_object_key: str) -> dict:
        if not context.get("source_object_key"):
            raise StorybookExperienceError("原始录音已清理，无法生成连续有声书")
        storyline = self.composer.compose(context)
        segments = self.composer.audio_segments(storyline, context["manifest"])
        try:
            metadata = self.renderer.render(
                context["source_object_key"], destination_object_key, segments
            )
        except PodcastRenderError as exc:
            raise StorybookExperienceError("连续有声书生成失败") from exc
        cues = metadata.pop("timeline", [])
        for scene in storyline["scenes"]:
            scene_cues = [cue for cue in cues if cue.get("page_index") == scene["page_index"]]
            scene["audio_start_ms"] = scene_cues[0]["start_ms"] if scene_cues else 0
            scene["audio_end_ms"] = scene_cues[-1]["end_ms"] if scene_cues else 0
        return {"storyline": storyline, "cues": cues, "metadata": metadata}
