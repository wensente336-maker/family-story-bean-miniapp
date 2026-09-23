import sys
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from scipy.io import wavfile

from app.config import Settings
from app.transcription import (
    AsrConfigurationError,
    ConservativeSpeakerDiarizer,
    DemoFamilyConversationProvider,
    MlxWhisperProvider,
    RecordingTranscriptionPipeline,
    build_asr_prompt,
    build_asr_provider,
)
from app.upload_storage import InvalidUploadToken, LocalObjectStorage


def provider(tmp_path, monkeypatch, raw):
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setitem(sys.modules, "mlx_whisper", SimpleNamespace(transcribe=lambda *_a, **_k: raw))
    return MlxWhisperProvider(Settings(asr_model_path=str(model)))


def test_asr_keeps_timestamps_words_and_confidence(tmp_path, monkeypatch) -> None:
    engine = provider(tmp_path, monkeypatch, {
        "language": "zh",
        "segments": [{
            "start": 1.25, "end": 2.5, "text": " 今天真开心 ",
            "no_speech_prob": 0.05, "avg_logprob": -0.2,
            "words": [
                {"word": "今天", "start": 1.25, "end": 1.7, "probability": 0.91},
                {"word": "真开心", "start": 1.7, "end": 2.5, "probability": 0.87},
            ],
        }],
    })
    result = engine.transcribe(tmp_path / "unused.wav")
    segment = result["segments"][0]
    assert segment["start_ms"] == 1250
    assert segment["end_ms"] == 2500
    assert segment["speaker_key"] == "speaker_a"
    assert segment["confidence"] == 0.89
    assert segment["words"][0]["text"] == "今天"


def test_asr_filters_high_no_speech_low_confidence_hallucination(tmp_path, monkeypatch) -> None:
    engine = provider(tmp_path, monkeypatch, {
        "language": "zh",
        "segments": [{
            "start": 0, "end": 5, "text": "幻觉文本", "no_speech_prob": 0.91,
            "avg_logprob": -2, "words": [
                {"word": "幻觉文本", "start": 0, "end": 5, "probability": 0.08}
            ],
        }],
    })
    assert engine.transcribe(tmp_path / "unused.wav")["segments"] == []


def test_asr_passes_family_vocabulary_prompt_to_large_v3_turbo(tmp_path, monkeypatch) -> None:
    model = tmp_path / "whisper-large-v3-turbo-mlx"
    model.mkdir()
    calls = []

    def transcribe(*_args, **kwargs):
        calls.append(kwargs)
        return {"language": "zh", "segments": []}

    monkeypatch.setitem(sys.modules, "mlx_whisper", SimpleNamespace(transcribe=transcribe))
    settings = Settings(
        asr_model_path=str(model),
        asr_initial_prompt="请忠实转写。",
    )
    prompt = build_asr_prompt(settings, {
        "title": "小猪佩奇去公园",
        "family_member_names": ["佩奇", "乔治", "佩奇"],
    })
    MlxWhisperProvider(settings).transcribe(tmp_path / "unused.wav", prompt)
    assert "小猪佩奇去公园" in prompt
    assert "佩奇、乔治" in prompt
    assert calls[0]["initial_prompt"] == prompt
    assert calls[0]["condition_on_previous_text"] is True


def test_asr_retries_only_low_confidence_segment_and_keeps_better_result(
    tmp_path, monkeypatch,
) -> None:
    model = tmp_path / "whisper-large-v3-turbo-mlx"
    model.mkdir()
    calls = []

    def transcribe(*_args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {"language": "zh", "segments": [{
                "start": 1.0, "end": 2.0, "text": "小猪配奇", "no_speech_prob": 0.0,
                "words": [{
                    "word": "小猪配奇", "start": 1.0, "end": 2.0, "probability": 0.31,
                }],
            }]}
        return {"language": "zh", "segments": [{
            "start": 1.0, "end": 2.0, "text": "小猪佩奇", "no_speech_prob": 0.0,
            "words": [{
                "word": "小猪佩奇", "start": 1.0, "end": 2.0, "probability": 0.93,
            }],
        }]}

    monkeypatch.setitem(sys.modules, "mlx_whisper", SimpleNamespace(transcribe=transcribe))
    engine = MlxWhisperProvider(Settings(
        asr_model_path=str(model), asr_low_confidence_threshold=0.65,
        asr_retry_enabled=True, asr_max_retry_segments=3,
    ))
    result = engine.transcribe(tmp_path / "unused.wav", "专有名词：小猪佩奇。")
    assert len(calls) == 2
    assert calls[1]["clip_timestamps"] == [0.65, 2.35]
    assert calls[1]["condition_on_previous_text"] is False
    assert result["segments"][0]["text"] == "小猪佩奇"
    assert result["second_pass_segments"] == 1


def test_demo_family_conversation_has_three_speakers_and_audio_bounded_timestamps(tmp_path) -> None:
    sample_rate = 16000
    path = tmp_path / "demo.wav"
    wavfile.write(path, sample_rate, np.zeros(sample_rate * 60, dtype=np.int16))
    result = DemoFamilyConversationProvider().transcribe(path)
    assert result["provider"] == "demo_family_conversation"
    assert len(result["segments"]) == 13
    assert {item["speaker_key"] for item in result["segments"]} == {
        "speaker_a", "speaker_b", "speaker_c"
    }
    assert result["segments"][0]["start_ms"] == 0
    assert result["segments"][-1]["end_ms"] == 60_000
    assert any("番茄拿铁" in item["text"] for item in result["segments"])


def test_demo_asr_is_rejected_outside_development_and_test() -> None:
    class Repository:
        def get_recording_internal(self, _recording_id):
            return {"object_key": "unused"}

    pipeline = RecordingTranscriptionPipeline(
        Settings(app_env="production", asr_provider="demo", allow_demo_asr=True),
        Repository(), object()
    )
    try:
        pipeline.process(uuid4())
    except AsrConfigurationError as exc:
        assert "ALLOW_DEMO_ASR" in str(exc)
    else:
        raise AssertionError("production must never use the deterministic demo transcript")


def test_demo_asr_requires_an_explicit_development_opt_in() -> None:
    with pytest.raises(AsrConfigurationError, match="ALLOW_DEMO_ASR"):
        build_asr_provider(Settings(app_env="development", asr_provider="demo"))
    provider = build_asr_provider(Settings(
        app_env="development", asr_provider="demo", allow_demo_asr=True,
    ))
    assert isinstance(provider, DemoFamilyConversationProvider)


def test_playback_token_is_short_lived_and_cannot_be_used_as_upload_token(tmp_path) -> None:
    settings = Settings(
        local_object_storage_path=str(tmp_path), auth_signing_key="test-signing-key",
        playback_token_ttl_seconds=60,
    )
    storage = LocalObjectStorage(settings)
    recording_id = uuid4()
    object_key = f"families/family/recordings/{recording_id}/source"
    token, expires_at = storage.issue_playback_token(recording_id, object_key)
    claims = storage.verify_playback_token(token)
    assert claims.recording_id == recording_id
    assert expires_at == claims.expires_at
    try:
        storage.verify_upload_token(token)
    except InvalidUploadToken:
        pass
    else:
        raise AssertionError("playback token must not be accepted for upload")


def test_conservative_diarizer_groups_distinct_acoustics_as_anonymous_speakers(tmp_path) -> None:
    sample_rate = 16000
    seconds = np.arange(sample_rate * 6) / sample_rate
    audio = np.concatenate([
        np.sin(2 * np.pi * 180 * seconds[:sample_rate * 2]),
        np.sin(2 * np.pi * 180 * seconds[:sample_rate * 2]),
        np.sin(2 * np.pi * 310 * seconds[:sample_rate * 2]),
    ])
    path = tmp_path / "speakers.wav"
    wavfile.write(path, sample_rate, (audio * 18000).astype(np.int16))
    segments = [
        {"start_ms": 0, "end_ms": 2000, "speaker_key": "speaker_a"},
        {"start_ms": 2000, "end_ms": 4000, "speaker_key": "speaker_a"},
        {"start_ms": 4000, "end_ms": 6000, "speaker_key": "speaker_a"},
    ]
    ConservativeSpeakerDiarizer().assign(path, segments)
    assert segments[0]["speaker_key"] == segments[1]["speaker_key"]
    assert segments[2]["speaker_key"] != segments[0]["speaker_key"]
    assert {item["speaker_key"] for item in segments} <= {
        "speaker_a", "speaker_b", "speaker_c"
    }
