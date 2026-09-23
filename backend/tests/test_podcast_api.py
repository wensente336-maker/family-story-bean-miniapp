from datetime import UTC, datetime
import base64
import json
import shutil
import subprocess
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.config import Settings
from app.podcast_audio import (
    LocalPodcastRenderer, SpeechSynthesisError, SynthesizedSpeech,
    VolcengineNarrationSynthesizer,
)
from app.podcast_repository import PostgresPodcastRepository
from app.podcast_router import get_podcast_repository


def make_podcast(moment_id):
    now = datetime.now(UTC)
    podcast_id = uuid4()
    segment_id = uuid4()
    return {
        "id": podcast_id, "recording_id": uuid4(), "moment_id": moment_id,
        "title": "家里的小剧场", "status": "COMPLETED", "version": 1,
        "pipeline_version": "storyboard-v1",
        "metadata": {
            "intro": "欢迎收听家庭故事豆。", "outro": "下一颗故事豆再见。",
            "duration_ms": 72000, "render_mode": "narrated", "voice_clone": False,
        },
        "moments": [{
            "id": moment_id, "title": "家庭晚餐", "theme": "欢乐", "position": 1,
            "start_ms": 3200, "end_ms": 7100,
        }],
        "segments": [
            {"id": uuid4(), "segment_index": 1, "kind": "narration", "label": "主持人开场", "text": "欢迎收听。"},
            {
                "id": uuid4(), "segment_index": 2, "kind": "original", "label": "家人真实原声",
                "text": "我们都笑了。", "source_moment_id": moment_id,
                "source_segment_id": segment_id, "start_ms": 3200, "end_ms": 7100,
            },
        ],
        "created_at": now, "updated_at": now, "object_key": "podcast.mp3",
    }


class MemoryPodcastRepository:
    def __init__(self, user_id):
        self.user_id = user_id
        self.moment_id = uuid4()
        self.podcast = make_podcast(self.moment_id)

    def create(self, user_id, moment_ids, _pipeline_version):
        return self.podcast if user_id == self.user_id and moment_ids == [self.moment_id] else None

    def get_for_user(self, user_id, podcast_id):
        return self.podcast if user_id == self.user_id and podcast_id == self.podcast["id"] else None

    def remix(self, user_id, podcast_id, moment_ids, intro, outro):
        if self.get_for_user(user_id, podcast_id) is None or moment_ids != [self.moment_id]:
            return None
        if self.podcast["metadata"]["intro"] == intro and self.podcast["metadata"]["outro"] == outro:
            return self.podcast
        self.podcast["version"] += 1
        self.podcast["metadata"].update({"intro": intro, "outro": outro})
        return self.podcast


@pytest.fixture()
def podcast_client():
    user_id = uuid4()
    repository = MemoryPodcastRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_podcast_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_create_podcast_from_kept_moments(podcast_client):
    client, repository = podcast_client
    response = client.post("/v1/podcasts", json={"moment_ids": [str(repository.moment_id)]})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["metadata"]["voice_clone"] is False
    assert data["segments"][1]["source_segment_id"] is not None


def test_remix_changes_version_once_and_identical_request_is_idempotent(podcast_client):
    client, repository = podcast_client
    payload = {
        "moment_ids": [str(repository.moment_id)],
        "intro": "新的开场旁白。", "outro": "新的片尾旁白。",
    }
    first = client.patch(f"/v1/podcasts/{repository.podcast['id']}", json=payload)
    second = client.patch(f"/v1/podcasts/{repository.podcast['id']}", json=payload)
    assert first.json()["data"]["version"] == 2
    assert second.json()["data"]["version"] == 2


def test_other_family_cannot_read_podcast(podcast_client):
    client, _repository = podcast_client
    response = client.get(f"/v1/podcasts/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PODCAST_NOT_FOUND"


def test_script_marks_only_original_audio_as_traceable():
    moment_id = uuid4()
    segment_id = uuid4()
    moments = [{
        "id": moment_id, "start_ms": 1000, "end_ms": 5000,
        "storyboard": {
            "scene": "家庭晚餐", "setup": "一家人正在吃饭。",
            "turning_point": "西红柿掉进了汤里。", "ending": "大家都笑了。",
            "emotion_curve": ["意外", "欢乐"], "highlight_quote": "我们都笑了。",
            "source_segments": [{"transcript_segment_id": str(segment_id)}],
        },
    }]
    segments = PostgresPodcastRepository._segments(moments, "开场", "片尾")
    original = [item for item in segments if item["kind"] == "original"]
    narration = [item for item in segments if item["kind"] == "narration"]
    assert len(original) == 1
    assert original[0]["source_segment_id"] == segment_id
    assert all(item.get("source_segment_id") is None for item in narration)


def test_renderer_falls_back_to_original_only_when_tts_is_unavailable(tmp_path, monkeypatch):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required")
    recording_id = uuid4()
    settings = Settings(
        local_object_storage_path=str(tmp_path), podcast_tts_provider="local",
        podcast_tts_fallback_to_system=False,
    )
    renderer = LocalPodcastRenderer(settings)
    source_key = f"families/{uuid4()}/recordings/{recording_id}/source"
    source = renderer.storage.path_for(source_key)
    source.parent.mkdir(parents=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=1", "-f", "wav", str(source),
    ], check=True)
    real_which = shutil.which
    monkeypatch.setattr(
        "app.podcast_audio.shutil.which",
        lambda command: None if command == "say" else real_which(command),
    )

    result = renderer.render(source_key, f"families/demo/recordings/{recording_id}/podcast.mp3", [
        {"kind": "narration", "text": "这段旁白应被跳过。"},
        {"kind": "original", "text": "真实原声", "start_ms": 0, "end_ms": 800},
    ])

    assert result["render_mode"] == "original_only"
    assert result["tts_provider"] is None
    assert result["duration_ms"] >= 800


def test_volcengine_tts_decodes_chunked_audio_and_keeps_credentials_in_headers(tmp_path):
    expected = b"ID3-natural-voice"

    def handler(request: httpx.Request):
        assert request.headers["x-api-app-key"] == "server-app"
        assert request.headers["x-api-app-id"] == "server-app"
        assert request.headers["x-api-access-key"] == "server-token"
        assert request.headers["x-api-resource-id"] == "seed-tts-2.0"
        payload = json.loads(request.content)
        assert payload["req_params"]["speaker"] == "zh_female_xiaohe_uranus_bigtts"
        body = "\n".join([
            json.dumps({"code": 0, "data": base64.b64encode(expected).decode()}),
            json.dumps({"code": 20000000, "message": "OK"}),
        ])
        return httpx.Response(200, text=body)

    settings = Settings(
        volcengine_tts_app_id="server-app", volcengine_tts_access_token="server-token"
    )
    synthesizer = VolcengineNarrationSynthesizer(
        settings, transport=httpx.MockTransport(handler)
    )
    result = synthesizer.synthesize("欢迎收听家庭故事豆。", tmp_path / "intro")

    assert result.path.read_bytes() == expected
    assert result.provider == "volcengine-doubao"
    assert result.voice == "zh_female_xiaohe_uranus_bigtts"


def test_renderer_records_natural_voice_provider(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required")

    class FakeNaturalVoice:
        provider = "volcengine-doubao"
        voice = "test-natural-voice"
        available = True

        def synthesize(self, _text, destination_stem):
            destination = destination_stem.with_suffix(".wav")
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                "-i", "sine=frequency=260:duration=0.25", "-f", "wav", str(destination),
            ], check=True)
            return SynthesizedSpeech(destination, self.provider, self.voice)

    recording_id = uuid4()
    settings = Settings(local_object_storage_path=str(tmp_path))
    renderer = LocalPodcastRenderer(settings, synthesizers=[FakeNaturalVoice()])
    source_key = f"families/{uuid4()}/recordings/{recording_id}/source"
    source = renderer.storage.path_for(source_key)
    source.parent.mkdir(parents=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=1", "-f", "wav", str(source),
    ], check=True)

    result = renderer.render(source_key, f"families/demo/recordings/{recording_id}/podcast.mp3", [
        {"kind": "narration", "text": "欢迎收听。"},
        {"kind": "original", "text": "真实原声", "start_ms": 0, "end_ms": 800},
    ])

    assert result["render_mode"] == "narrated"
    assert result["tts_provider"] == "volcengine-doubao"
    assert result["tts_quality"] == "neural-natural"
    assert result["tts_fallback_used"] is False


def test_renderer_uses_coherent_original_only_cut_when_tts_fails_mid_story(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required")

    class FailsOnSecondNarration:
        provider = "unstable-natural-voice"
        voice = "test-voice"
        available = True

        def __init__(self):
            self.calls = 0

        def synthesize(self, _text, destination_stem):
            self.calls += 1
            if self.calls == 2:
                raise SpeechSynthesisError("provider stopped midway")
            destination = destination_stem.with_suffix(".wav")
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                "-i", "sine=frequency=260:duration=0.2", "-f", "wav", str(destination),
            ], check=True)
            return SynthesizedSpeech(destination, self.provider, self.voice)

    recording_id = uuid4()
    settings = Settings(local_object_storage_path=str(tmp_path))
    renderer = LocalPodcastRenderer(settings, synthesizers=[FailsOnSecondNarration()])
    source_key = f"families/{uuid4()}/recordings/{recording_id}/source"
    source = renderer.storage.path_for(source_key)
    source.parent.mkdir(parents=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=1", "-f", "wav", str(source),
    ], check=True)

    result = renderer.render(source_key, f"families/demo/recordings/{recording_id}/podcast.mp3", [
        {"kind": "narration", "text": "开场。"},
        {"kind": "original", "text": "真实原声", "start_ms": 0, "end_ms": 350},
        {"kind": "narration", "text": "收尾。"},
        {"kind": "original", "text": "另一段原声", "start_ms": 350, "end_ms": 800},
    ])

    assert result["render_mode"] == "original_only"
    assert result["narration_segments"] == 0
    assert result["tts_fallback_used"] is True
    assert [item["kind"] for item in result["timeline"]] == ["original", "original"]
    assert result["ducking_enabled"] is True
