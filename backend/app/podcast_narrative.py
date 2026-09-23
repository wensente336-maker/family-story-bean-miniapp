from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Protocol

import httpx

from .podcast_contracts import PodcastMaterialData


class InvalidPodcastPlan(ValueError):
    """Raised when a generated script breaks the sound-story truth contract."""


class PodcastNarrativeGenerator(Protocol):
    provider: str
    model_version: str
    prompt_version: str

    def generate(
        self,
        recording_title: str,
        materials: list[PodcastMaterialData],
        narration_style: str,
    ) -> dict: ...


STYLE_COPY = {
    "warm": {
        "description": "用温柔的第三人称解说，串起家人亲口留下的声音。",
        "music": "warm-acoustic-light",
        "intro": "这是一个被家人亲口记住的时刻。",
        "bridge": "故事继续，接下来听见{speaker}留下的声音。",
        "outro": "声音停在这里，这个家庭时刻已经被好好收藏。",
    },
    "humorous": {
        "description": "用轻松俏皮的第三人称串讲，保留家人的真实笑点。",
        "music": "playful-ukulele-light",
        "intro": "这一回，家里的日常悄悄有了喜剧节奏。",
        "bridge": "故事的下一棒，交到了{speaker}手里。",
        "outro": "笑声告一段落，这段家庭趣事正式入选珍藏。",
    },
    "growth": {
        "description": "用成长记录式的第三人称解说，陪伴家人回听这一刻。",
        "music": "gentle-piano-light",
        "intro": "成长常常藏在这些真实而短暂的声音里。",
        "bridge": "沿着声音往前，{speaker}留下了这一段。",
        "outro": "今天的声音会成为明天回望成长的一枚坐标。",
    },
    "documentary": {
        "description": "用克制的第三人称记录口吻，按时间保留家庭原声。",
        "music": "minimal-documentary-light",
        "intro": "这段记录按照家人的真实声音展开。",
        "bridge": "时间继续向前，随后出现的是{speaker}的声音。",
        "outro": "本段记录结束，所有原声均可追溯至已确认素材。",
    },
}


@dataclass(frozen=True)
class SafePodcastNarrativeGenerator:
    provider: str = "safe-template"
    model_version: str = "sound-story-safe-v1"
    prompt_version: str = "podcast-narrative-v1"
    narrator_voice: str = "zh_female_xiaohe_uranus_bigtts"

    def generate(
        self,
        recording_title: str,
        materials: list[PodcastMaterialData],
        narration_style: str,
    ) -> dict:
        if not materials:
            raise InvalidPodcastPlan("至少需要一段已确认声音素材")
        if narration_style not in STYLE_COPY:
            raise InvalidPodcastPlan("不支持的串讲风格")
        ordered = sorted(materials, key=lambda item: item.position)
        copy = STYLE_COPY[narration_style]
        segments: list[dict] = []

        def append(kind: str, label: str, text: str, source_ids: list):
            segments.append({
                "segment_index": len(segments) + 1,
                "kind": kind,
                "label": label,
                "text": text,
                "source_material_ids": source_ids,
            })

        append("narration", "第三人称开场", copy["intro"], [str(ordered[0].id)])
        for index, material in enumerate(ordered):
            if index:
                append(
                    "narration",
                    "第三人称串讲",
                    copy["bridge"].format(speaker=material.speaker_label),
                    [str(ordered[index - 1].id), str(material.id)],
                )
            append(
                "original",
                f"{material.speaker_label}的家庭原声",
                material.confirmed_text,
                [str(material.id)],
            )
        append("narration", "第三人称收尾", copy["outro"], [str(ordered[-1].id)])

        plan = {
            "title": recording_title.strip() or "一段家庭声音故事",
            "description": copy["description"],
            "narrator_voice": self.narrator_voice,
            "music_style": copy["music"],
            "narration_style": narration_style,
            "generator_provider": self.provider,
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
            "external_share_allowed": all(item.share_allowed for item in ordered),
            "segments": segments,
        }
        plan["safety_checks"] = validate_podcast_plan(plan, ordered)
        return plan


@dataclass(frozen=True)
class OpenAICompatibleNarrativeGenerator:
    """Adapter for an OpenAI-compatible chat endpoint; secrets never enter plans."""

    endpoint: str
    api_key: str
    model_version: str
    provider: str
    timeout_seconds: float = 45.0
    prompt_version: str = "podcast-narrative-v1"
    transport: httpx.BaseTransport | None = None

    def generate(self, recording_title, materials, narration_style):
        source = [{
            "material_id": str(item.id),
            "position": item.position,
            "speaker": item.speaker_label,
            "role": item.role,
            "confirmed_text": item.confirmed_text,
            "share_allowed": item.share_allowed,
        } for item in sorted(materials, key=lambda item: item.position)]
        instruction = (
            "你是家庭声音播客编辑。只根据提供的确认素材写第三人称串讲。"
            "不得补写事件、冒充家人或创造直接引语。原声段 text 必须逐字复制 confirmed_text。"
            "每段必须给出 source_material_ids。输出纯 JSON，字段为 title、description、"
            "music_style、segments；segments 每项包含 kind、label、text、source_material_ids。"
            "播放顺序应由解说自然串起全部原声，且原声按 position 排列。"
        )
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_version,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": json.dumps({
                            "recording_title": recording_title,
                            "narration_style": narration_style,
                            "materials": source,
                        }, ensure_ascii=False)},
                    ],
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        candidate = json.loads(content)
        if not isinstance(candidate, dict):
            raise InvalidPodcastPlan("模型没有返回对象结构")
        for field in ("title", "description", "music_style"):
            if not isinstance(candidate.get(field), str) or not candidate[field].strip():
                raise InvalidPodcastPlan(f"模型输出缺少 {field}")
        if not isinstance(candidate.get("segments"), list):
            raise InvalidPodcastPlan("模型输出缺少 segments")
        if any(
            not isinstance(segment, dict)
            or not isinstance(segment.get("label"), str)
            or not isinstance(segment.get("text"), str)
            or segment.get("kind") not in {"narration", "original"}
            for segment in candidate["segments"]
        ):
            raise InvalidPodcastPlan("模型段落结构无效")
        for index, segment in enumerate(candidate.get("segments") or [], start=1):
            segment["segment_index"] = index
        candidate.update({
            "narrator_voice": "zh_female_xiaohe_uranus_bigtts",
            "narration_style": narration_style,
            "generator_provider": self.provider,
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
            "external_share_allowed": all(item.share_allowed for item in materials),
        })
        candidate["safety_checks"] = validate_podcast_plan(candidate, materials)
        return candidate


@dataclass(frozen=True)
class ResilientPodcastNarrativeGenerator:
    """Uses an optional AI adapter, but never returns an untraceable script."""

    primary: PodcastNarrativeGenerator | None
    fallback: PodcastNarrativeGenerator

    @property
    def provider(self) -> str:
        return self.primary.provider if self.primary else self.fallback.provider

    @property
    def model_version(self) -> str:
        return self.primary.model_version if self.primary else self.fallback.model_version

    @property
    def prompt_version(self) -> str:
        return self.primary.prompt_version if self.primary else self.fallback.prompt_version

    def generate(self, recording_title, materials, narration_style):
        if self.primary is not None:
            try:
                candidate = self.primary.generate(recording_title, materials, narration_style)
                candidate["safety_checks"] = validate_podcast_plan(candidate, materials)
                return candidate
            except Exception:
                pass
        return self.fallback.generate(recording_title, materials, narration_style)


def validate_podcast_plan(plan: dict, materials: list[PodcastMaterialData]) -> dict[str, bool]:
    ordered = sorted(materials, key=lambda item: item.position)
    by_id = {str(item.id): item for item in ordered}
    segments = plan.get("segments") or []
    if len(segments) < 3:
        raise InvalidPodcastPlan("串讲脚本至少需要三个段落")

    indices_ok = [segment.get("segment_index") for segment in segments] == list(
        range(1, len(segments) + 1)
    )
    sources_ok = all(
        segment.get("source_material_ids")
        and set(segment["source_material_ids"]).issubset(by_id)
        for segment in segments
    )
    originals = [segment for segment in segments if segment.get("kind") == "original"]
    originals_exact = len(originals) == len(ordered) and all(
        len(segment.get("source_material_ids") or []) == 1
        and segment.get("text")
        == by_id[segment["source_material_ids"][0]].confirmed_text
        for segment in originals
    )
    original_order = [segment["source_material_ids"][0] for segment in originals] == [
        str(item.id) for item in ordered
    ]
    confirmed_quotes = [item.confirmed_text for item in ordered if len(item.confirmed_text) >= 6]
    narration_has_no_copied_quote = all(
        not any(quote in segment.get("text", "") for quote in confirmed_quotes)
        for segment in segments
        if segment.get("kind") == "narration"
    )
    sharing_matches = plan.get("external_share_allowed") == all(
        item.share_allowed for item in ordered
    )
    text_to_check = " ".join(segment.get("text", "") for segment in segments)
    sensitive_pattern = re.compile(
        r"(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    )
    sensitive_info_clear = (
        not sensitive_pattern.search(text_to_check)
        or plan.get("external_share_allowed") is False
    )
    checks = {
        "sequential_segments": indices_ok,
        "all_segments_traceable": sources_ok,
        "original_quotes_exact": originals_exact,
        "original_order_preserved": original_order,
        "narration_has_no_copied_quote": narration_has_no_copied_quote,
        "sharing_policy_inherited": sharing_matches,
        "sensitive_information_guard": sensitive_info_clear,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise InvalidPodcastPlan(f"串讲脚本安全校验失败：{', '.join(failed)}")
    return checks
