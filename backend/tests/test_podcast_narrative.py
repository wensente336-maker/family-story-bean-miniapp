from uuid import uuid4

import httpx
import pytest

from app.podcast_contracts import PodcastMaterialData
from app.podcast_narrative import (
    ResilientPodcastNarrativeGenerator,
    SafePodcastNarrativeGenerator,
    OpenAICompatibleNarrativeGenerator,
    validate_podcast_plan,
)


def material(position: int, suffix: int, share_allowed: bool = True):
    labels = ["苗苗", "妈妈", "爸爸"]
    quotes = [
        f"第 {suffix} 颗西红柿差点飞到奶奶家。",
        f"先把桌子擦干净，这是第 {suffix} 次提醒。",
        f"今晚最好记的是第 {suffix} 个家庭笑话。",
    ]
    return PodcastMaterialData(
        id=uuid4(),
        source_moment_id=uuid4(),
        source_recording_id=uuid4(),
        source_segment_id=uuid4(),
        family_member_id=uuid4(),
        speaker_key=f"speaker_{position}",
        speaker_label=labels[position - 1],
        role=["setup", "highlight", "ending"][position - 1],
        position=position,
        start_ms=(position - 1) * 10_000,
        end_ms=position * 10_000,
        original_text=quotes[position - 1],
        confirmed_text=quotes[position - 1],
        share_allowed=share_allowed,
    )


@pytest.mark.parametrize(
    ("fixture_index", "style"),
    [(index, style) for index in range(10) for style in ("warm", "humorous", "growth")],
)
def test_thirty_story_fixtures_keep_quotes_exact_and_every_segment_traceable(
    fixture_index, style
):
    materials = [material(position, fixture_index) for position in range(1, 4)]
    plan = SafePodcastNarrativeGenerator().generate("周日晚餐", materials, style)
    checks = validate_podcast_plan(plan, materials)

    assert all(checks.values())
    originals = [segment for segment in plan["segments"] if segment["kind"] == "original"]
    assert [segment["text"] for segment in originals] == [
        item.confirmed_text for item in materials
    ]
    assert all(segment["source_material_ids"] for segment in plan["segments"])


def test_three_styles_produce_distinct_narration_and_music():
    materials = [material(position, 1) for position in range(1, 4)]
    plans = {
        style: SafePodcastNarrativeGenerator().generate("周日晚餐", materials, style)
        for style in ("warm", "humorous", "growth")
    }
    assert len({plan["segments"][0]["text"] for plan in plans.values()}) == 3
    assert len({plan["music_style"] for plan in plans.values()}) == 3


def test_private_material_disables_external_sharing():
    materials = [material(1, 1), material(2, 1, share_allowed=False)]
    plan = SafePodcastNarrativeGenerator().generate("周日晚餐", materials, "warm")
    assert plan["external_share_allowed"] is False
    assert plan["safety_checks"]["sharing_policy_inherited"] is True


def test_short_original_quote_can_match_a_speaker_name_without_false_alarm():
    item = material(1, 1)
    item.confirmed_text = "妈妈"
    plan = SafePodcastNarrativeGenerator().generate("周日晚餐", [item], "warm")
    assert [segment["text"] for segment in plan["segments"] if segment["kind"] == "original"] == ["妈妈"]


class UnsafeGenerator:
    provider = "unsafe-ai"
    model_version = "bad-v1"
    prompt_version = "bad-prompt"

    def generate(self, recording_title, materials, narration_style):
        return {
            "external_share_allowed": True,
            "segments": [{
                "segment_index": 1,
                "kind": "original",
                "label": "伪造原声",
                "text": "这句话从未说过",
                "source_material_ids": [str(materials[0].id)],
            }],
        }


def test_invalid_ai_output_falls_back_to_safe_traceable_script():
    materials = [material(position, 2) for position in range(1, 4)]
    generator = ResilientPodcastNarrativeGenerator(
        primary=UnsafeGenerator(), fallback=SafePodcastNarrativeGenerator()
    )
    plan = generator.generate("周日晚餐", materials, "warm")
    assert plan["generator_provider"] == "safe-template"
    assert all(plan["safety_checks"].values())


@pytest.mark.parametrize("content", ["not-json", "{}"])
def test_invalid_model_response_always_falls_back(content):
    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    materials = [material(position, 3) for position in range(1, 4)]
    primary = OpenAICompatibleNarrativeGenerator(
        endpoint="https://model.invalid/v1/chat/completions",
        api_key="test-only",
        model_version="model-test",
        provider="compatible-test",
        transport=httpx.MockTransport(handler),
    )
    plan = ResilientPodcastNarrativeGenerator(
        primary=primary, fallback=SafePodcastNarrativeGenerator()
    ).generate("周日晚餐", materials, "growth")
    assert plan["generator_provider"] == "safe-template"
    assert all(plan["safety_checks"].values())
