from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth_router import current_user_id
from app.main import app
from app.recording_router import get_recording_repository
from app.recording_router import get_object_storage
from app.config import Settings
from app.transcript_router import get_transcript_repository
from app.upload_storage import LocalObjectStorage


class MemoryTranscriptRepository:
    def __init__(self, user_id):
        now = datetime.now(UTC)
        self.user_id = user_id
        self.recording_id = uuid4()
        self.member_id = uuid4()
        self.segment = {
            "id": uuid4(), "recording_id": self.recording_id,
            "family_member_id": None, "speaker_key": "speaker_a",
            "start_ms": 1000, "end_ms": 2400, "text": "今天真开心",
            "original_text": "今天真开心", "confidence": 0.58,
            "words": [], "edited_by_user": False, "pipeline_version": "storyboard-v1",
            "created_at": now, "updated_at": now,
        }

    def get_for_user(self, user_id, recording_id):
        if user_id != self.user_id or recording_id != self.recording_id:
            return None
        return {
            "recording": {
                "id": self.recording_id, "title": "周日晚餐", "duration_ms": 5000,
                "transcript_language": "zh", "asr_provider": "mlx_whisper",
                "asr_model": "whisper-base-mlx", "transcript_revision": 1,
            },
            "segments": [self.segment],
            "speakers": [{
                "speaker_key": "speaker_a", "family_member_id": None,
                "display_name": "说话人 A",
            }],
            "members": [{"id": self.member_id, "nickname": "妈妈"}],
        }

    def update_segment(self, user_id, recording_id, segment_id, text, speaker_key):
        if self.get_for_user(user_id, recording_id) is None or segment_id != self.segment["id"]:
            return None
        if text is not None:
            self.segment.update(text=text, edited_by_user=True)
        if speaker_key is not None:
            self.segment["speaker_key"] = speaker_key
        return self.segment

    def set_speaker_mapping(
        self, user_id, recording_id, speaker_key, family_member_id, display_name
    ):
        if self.get_for_user(user_id, recording_id) is None:
            return None
        if family_member_id not in (None, self.member_id):
            return None
        self.segment["family_member_id"] = family_member_id
        return {
            "speaker_key": speaker_key, "family_member_id": family_member_id,
            "display_name": "妈妈" if family_member_id else display_name,
        }


@pytest.fixture()
def transcript_client():
    user_id = uuid4()
    repository = MemoryTranscriptRepository(user_id)
    app.dependency_overrides[current_user_id] = lambda: user_id
    app.dependency_overrides[get_transcript_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_transcript_returns_timestamps_confidence_and_members(transcript_client) -> None:
    client, repository = transcript_client
    response = client.get(f"/v1/recordings/{repository.recording_id}/transcript")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["segments"][0]["start_ms"] == 1000
    assert data["segments"][0]["confidence"] == 0.58
    assert data["family_members"][0]["nickname"] == "妈妈"


def test_transcript_text_edit_and_speaker_mapping_are_persisted(transcript_client) -> None:
    client, repository = transcript_client
    edited = client.patch(
        f"/v1/recordings/{repository.recording_id}/transcript/segments/{repository.segment['id']}",
        json={"text": "今天特别开心"},
    )
    mapped = client.put(
        f"/v1/recordings/{repository.recording_id}/speakers/speaker_a",
        json={"family_member_id": str(repository.member_id), "display_name": "妈妈"},
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["edited_by_user"] is True
    assert mapped.status_code == 200
    assert mapped.json()["data"]["display_name"] == "妈妈"


def test_other_recording_transcript_is_not_exposed(transcript_client) -> None:
    client, _repository = transcript_client
    response = client.get(f"/v1/recordings/{uuid4()}/transcript")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TRANSCRIPT_NOT_FOUND"


def test_expired_original_audio_returns_explicit_gone_response(transcript_client) -> None:
    client, repository = transcript_client

    class ExpiredRecordingRepository:
        def get_recording(self, user_id, recording_id):
            if user_id == repository.user_id and recording_id == repository.recording_id:
                return {"id": recording_id, "object_key": None, "media_type": "audio/mpeg"}
            return None

    app.dependency_overrides[get_recording_repository] = lambda: ExpiredRecordingRepository()
    response = client.post(f"/v1/recordings/{repository.recording_id}/playback-url")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "ORIGINAL_AUDIO_PURGED"


def test_missing_original_object_returns_explicit_gone_response(
    transcript_client, tmp_path,
) -> None:
    client, repository = transcript_client

    class MissingObjectRecordingRepository:
        def get_recording(self, user_id, recording_id):
            if user_id == repository.user_id and recording_id == repository.recording_id:
                return {
                    "id": recording_id,
                    "object_key": "families/family/recordings/missing/source",
                    "media_type": "audio/mpeg",
                }
            return None

    storage = LocalObjectStorage(Settings(local_object_storage_path=str(tmp_path)))
    app.dependency_overrides[get_recording_repository] = lambda: MissingObjectRecordingRepository()
    app.dependency_overrides[get_object_storage] = lambda: storage
    response = client.post(f"/v1/recordings/{repository.recording_id}/playback-url")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "ORIGINAL_AUDIO_PURGED"
