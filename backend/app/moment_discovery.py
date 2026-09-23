from __future__ import annotations

import math
import re
from dataclasses import dataclass


HUMOR_WORDS = ("笑", "好玩", "搞笑", "哈哈", "掉", "拿错", "尴尬")
WARM_WORDS = ("爱", "喜欢", "谢谢", "想你", "陪", "开心", "幸福", "记得")
SURPRISE_WORDS = ("竟然", "突然", "没想到", "原来", "真的", "太", "第一次")
SENSITIVE_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "address": re.compile(r"(?:路|街|弄|小区|单元|楼|室)"),
}


@dataclass
class Candidate:
    segments: list[dict]
    score: float
    breakdown: dict[str, float]

    @property
    def start_ms(self) -> int:
        return self.segments[0]["start_ms"]

    @property
    def end_ms(self) -> int:
        return self.segments[-1]["end_ms"]


class ExplainableMomentRanker:
    """Deterministic MVP ranker whose score can be shown and regression-tested."""

    def _score(self, segments: list[dict]) -> tuple[float, dict[str, float]]:
        text = "".join(segment["text"] for segment in segments)
        speakers = {segment["speaker_key"] for segment in segments}
        duration = max(1, segments[-1]["end_ms"] - segments[0]["start_ms"])
        humor = min(1.0, sum(text.count(word) for word in HUMOR_WORDS) / 2)
        warmth = min(1.0, sum(text.count(word) for word in WARM_WORDS) / 2)
        surprise = min(1.0, sum(text.count(word) for word in SURPRISE_WORDS) / 2)
        expression = min(1.0, (text.count("！") + text.count("!") + text.count("？") + text.count("?")) / 2)
        participation = min(1.0, len(speakers) / 3)
        completeness = min(1.0, len(segments) / 3) * min(1.0, duration / 12000)
        confidence_values = [float(item["confidence"]) for item in segments if item.get("confidence") is not None]
        reliability = sum(confidence_values) / len(confidence_values) if confidence_values else 0.5
        breakdown = {
            "humor": round(humor, 4), "warmth": round(warmth, 4),
            "surprise": round(surprise, 4), "expression": round(expression, 4),
            "participation": round(participation, 4),
            "completeness": round(completeness, 4), "reliability": round(reliability, 4),
        }
        score = (
            humor * 0.20 + warmth * 0.18 + surprise * 0.14 + expression * 0.10
            + participation * 0.13 + completeness * 0.15 + reliability * 0.10
        )
        return round(max(0.0, min(1.0, score)), 4), breakdown

    def rank(self, segments: list[dict], limit: int = 3) -> list[Candidate]:
        if not segments:
            return []
        if len(segments) <= limit:
            single_candidates = [
                Candidate([item], *self._score([item])) for item in segments
            ]
            return sorted(single_candidates, key=lambda item: (-item.score, item.start_ms))
        windows: list[Candidate] = []
        for index in range(len(segments)):
            for size in range(1, min(4, len(segments) - index + 1)):
                group = segments[index:index + size]
                if group[-1]["end_ms"] - group[0]["start_ms"] > 45000:
                    break
                score, breakdown = self._score(group)
                windows.append(Candidate(group, score, breakdown))
        windows.sort(key=lambda item: (-item.score, item.start_ms, item.end_ms))
        selected: list[Candidate] = []
        for candidate in windows:
            overlaps = any(
                max(candidate.start_ms, chosen.start_ms) < min(candidate.end_ms, chosen.end_ms)
                for chosen in selected
            )
            if not overlaps:
                selected.append(candidate)
            if len(selected) == limit:
                break
        if len(selected) < min(limit, len(segments)):
            for segment in segments:
                candidate = Candidate([segment], *self._score([segment]))
                if all(candidate.start_ms != item.start_ms for item in selected):
                    selected.append(candidate)
                if len(selected) == limit:
                    break
        return sorted(selected, key=lambda item: (-item.score, item.start_ms))


class StoryboardBuilder:
    @staticmethod
    def _theme(text: str) -> tuple[str, str, list[str]]:
        if any(word in text for word in HUMOR_WORDS):
            return "家庭趣事", "欢乐", ["日常", "意外", "大笑", "回味"]
        if any(word in text for word in WARM_WORDS):
            return "温暖时刻", "温暖", ["平静", "倾听", "感动", "温暖"]
        return "成长日常", "日常", ["好奇", "分享", "回应", "记住"]

    def build(self, recording: dict, candidate: Candidate, speaker_names: dict[str, dict], pipeline_version: str) -> dict:
        segments = candidate.segments
        full_text = "".join(item["text"] for item in segments)
        story_type, theme, curve = self._theme(full_text)
        quote_segment = max(segments, key=lambda item: (len(item["text"]), item.get("confidence") or 0))
        quote = quote_segment["text"]
        short_quote = quote if len(quote) <= 26 else quote[:25] + "…"
        characters = []
        for speaker_key in dict.fromkeys(item["speaker_key"] for item in segments):
            mapping = speaker_names.get(speaker_key, {})
            characters.append({
                "family_member_id": str(mapping["family_member_id"]) if mapping.get("family_member_id") else None,
                "speaker_key": speaker_key,
                "display_name": mapping.get("display_name") or speaker_key.replace("speaker_", "说话人 ").upper(),
            })
        sensitive = [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(full_text)]
        return {
            "schema_version": "1.0", "pipeline_version": pipeline_version,
            "title": f"「{short_quote}」的家庭时刻", "scene": recording.get("scene_type") or "一次家庭对话",
            "story_type": story_type, "characters": characters,
            "setup": segments[0]["text"],
            "turning_point": segments[len(segments) // 2]["text"],
            "ending": segments[-1]["text"], "highlight_quote": quote,
            "emotion_curve": curve,
            "source_segments": [{
                "transcript_segment_id": str(item["id"]), "start_ms": item["start_ms"],
                "end_ms": item["end_ms"], "quote": item["text"],
            } for item in segments],
            "sensitive_flags": sensitive, "confidence": round(candidate.score, 4),
            "_theme": theme,
        }


class MomentDiscoveryService:
    def __init__(self, repository, pipeline_version: str):
        self.repository = repository
        self.pipeline_version = pipeline_version
        self.ranker = ExplainableMomentRanker()
        self.builder = StoryboardBuilder()

    def process(self, recording_id):
        source = self.repository.load_source(recording_id)
        if source is None:
            raise ValueError("recording transcript not found")
        duration_ms = int(source["recording"].get("duration_ms") or 0)
        if duration_ms <= 5 * 60_000:
            limit = 5
        elif duration_ms <= 10 * 60_000:
            limit = 7
        elif duration_ms <= 15 * 60_000:
            limit = 10
        elif duration_ms <= 30 * 60_000:
            limit = 15
        else:
            limit = 20
        candidates = self.ranker.rank(source["segments"], limit=limit)
        moments = []
        for rank, candidate in enumerate(candidates, start=1):
            storyboard = self.builder.build(
                source["recording"], candidate, source["speaker_names"], self.pipeline_version
            )
            theme = storyboard.pop("_theme")
            moments.append({
                "rank": rank, "start_ms": candidate.start_ms, "end_ms": candidate.end_ms,
                "title": storyboard["title"], "theme": theme, "score": candidate.score,
                "score_breakdown": candidate.breakdown, "storyboard": storyboard,
            })
        self.repository.replace_moments(
            recording_id, moments, self.pipeline_version,
            source["recording"].get("transcript_revision", 0),
        )
        return moments
