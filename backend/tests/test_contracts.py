import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import JobStage, SourceSegment, Storyboard
from app.podcast_contracts import (
    PODCAST_VERSION_TRANSITIONS,
    PodcastMaterialData,
    PodcastVersionStatus,
    can_transition_podcast_version,
)


ROOT = Path(__file__).resolve().parents[1]


def test_storyboard_example_matches_pydantic_contract() -> None:
    payload = json.loads((ROOT / "contracts/storyboard.example.json").read_text(encoding="utf-8"))
    storyboard = Storyboard.model_validate(payload)
    assert storyboard.schema_version == "1.0"
    assert storyboard.source_segments[0].quote == storyboard.highlight_quote


def test_source_segment_rejects_invalid_time_range() -> None:
    with pytest.raises(ValidationError):
        SourceSegment(
            transcript_segment_id="66666666-6666-4666-8666-666666666666",
            start_ms=1000,
            end_ms=1000,
            quote="invalid",
        )


def test_json_schema_has_required_traceability_fields() -> None:
    schema = json.loads((ROOT / "contracts/storyboard.schema.json").read_text(encoding="utf-8"))
    source_schema = schema["properties"]["source_segments"]["items"]
    assert {"transcript_segment_id", "start_ms", "end_ms", "quote"}.issubset(
        source_schema["required"]
    )


def test_job_state_machine_matches_api_enum() -> None:
    state_machine = json.loads(
        (ROOT / "contracts/job-state-machine.json").read_text(encoding="utf-8")
    )
    declared_states = set(state_machine["transitions"])
    assert declared_states == {stage.value for stage in JobStage}
    assert set(state_machine["terminal"]).issubset(declared_states)


def test_podcast_state_machine_matches_api_enum() -> None:
    state_machine = json.loads(
        (ROOT / "contracts/podcast-state-machine.json").read_text(encoding="utf-8")
    )
    declared_states = set(state_machine["transitions"])
    assert declared_states == {state.value for state in PodcastVersionStatus}
    for state, targets in PODCAST_VERSION_TRANSITIONS.items():
        assert set(state_machine["transitions"][state.value]) == {
            target.value for target in targets
        }
    assert can_transition_podcast_version(
        PodcastVersionStatus.DRAFT, PodcastVersionStatus.CONFIRMED
    )
    assert not can_transition_podcast_version(
        PodcastVersionStatus.COMPLETED, PodcastVersionStatus.GENERATING
    )


def test_podcast_material_rejects_invalid_audio_range() -> None:
    with pytest.raises(ValidationError):
        PodcastMaterialData(
            id="11111111-1111-4111-8111-111111111111",
            source_recording_id="22222222-2222-4222-8222-222222222222",
            source_segment_id="33333333-3333-4333-8333-333333333333",
            speaker_key="SPEAKER_00",
            speaker_label="妈妈",
            role="highlight",
            position=1,
            start_ms=3200,
            end_ms=3200,
            original_text="原始转写",
            confirmed_text="用户确认文本",
        )
