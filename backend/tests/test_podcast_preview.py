from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.podcast_audio import SynthesizedSpeech
from app.podcast_preview import LocalNarrationPreviewService
from app.upload_storage import LocalObjectStorage


class FakeSynthesizer:
    provider = "fake-natural-tts"
    voice = "fake-voice"
    available = True

    def __init__(self):
        self.calls = 0

    def synthesize(self, text: str, destination_stem: Path):
        self.calls += 1
        destination = destination_stem.with_suffix(".mp3")
        destination.write_bytes(b"ID3-preview")
        return SynthesizedSpeech(destination, self.provider, self.voice)


def test_narration_preview_is_cached_and_uses_signed_private_url(tmp_path):
    settings = Settings(
        local_object_storage_path=str(tmp_path),
        auth_signing_key="preview-test-key",
    )
    synth = FakeSynthesizer()
    service = LocalNarrationPreviewService(settings, synthesizers=[synth])
    recording_id = uuid4()
    family_id = uuid4()

    first = service.create(recording_id, family_id, "这是短试听。", "chosen-voice")
    second = service.create(recording_id, family_id, "这是短试听。", "chosen-voice")

    assert synth.calls == 1
    assert first["provider"] == "fake-natural-tts"
    assert second["provider"] == "preview-cache"
    claims = LocalObjectStorage(settings).verify_playback_token(second["token"])
    assert claims.recording_id == recording_id
    assert f"families/{family_id}/recordings/{recording_id}/podcast-previews/" in claims.object_key

