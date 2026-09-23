from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import UUID

from .config import Settings
from .podcast_audio import (
    MacOsNarrationSynthesizer,
    NarrationSynthesizer,
    SpeechSynthesisError,
    VolcengineNarrationSynthesizer,
)
from .upload_storage import LocalObjectStorage


class NarrationPreviewService(Protocol):
    def create(
        self, recording_id: UUID, family_id: UUID, text: str, voice: str
    ) -> dict: ...


class LocalNarrationPreviewService:
    def __init__(
        self,
        settings: Settings,
        synthesizers: list[NarrationSynthesizer] | None = None,
    ):
        self.settings = settings
        self.storage = LocalObjectStorage(settings)
        self.synthesizers = synthesizers

    def create(self, recording_id, family_id, text, voice):
        preview_text = text.strip()[:120]
        if not preview_text:
            raise SpeechSynthesisError("解说文字为空")
        digest = hashlib.sha256(f"{voice}\0{preview_text}".encode()).hexdigest()[:24]
        object_key = (
            f"families/{family_id}/recordings/{recording_id}/"
            f"podcast-previews/{digest}.mp3"
        )
        destination = self.storage.path_for(object_key)
        provider = "preview-cache"
        resolved_voice = voice
        synthesizers = self.synthesizers
        if synthesizers is None:
            voice_settings = self.settings.model_copy(update={"volcengine_tts_voice": voice})
            doubao = VolcengineNarrationSynthesizer(voice_settings)
            synthesizers = []
            if doubao.available:
                synthesizers.append(doubao)
            if self.settings.podcast_tts_fallback_to_system:
                synthesizers.append(MacOsNarrationSynthesizer())
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            last_error: Exception | None = None
            with tempfile.TemporaryDirectory(prefix="storybean-preview-") as temporary:
                stem = Path(temporary) / "narration-preview"
                for synthesizer in synthesizers:
                    if not synthesizer.available:
                        continue
                    try:
                        speech = synthesizer.synthesize(preview_text, stem)
                        if speech.path.suffix.lower() == ".mp3":
                            shutil.copyfile(speech.path, destination)
                        else:
                            try:
                                subprocess.run(
                                    [
                                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                                        "-i", str(speech.path), "-c:a", "libmp3lame",
                                        "-b:a", "96k", str(destination),
                                    ],
                                    check=True, capture_output=True, text=True,
                                )
                            except (OSError, subprocess.CalledProcessError) as exc:
                                raise SpeechSynthesisError("解说试听音频转码失败") from exc
                        provider = speech.provider
                        resolved_voice = speech.voice
                        break
                    except SpeechSynthesisError as exc:
                        last_error = exc
                else:
                    raise SpeechSynthesisError(
                        str(last_error) if last_error else "没有可用的解说试听音色"
                    )
        token, expires_at = self.storage.issue_playback_token(
            recording_id, object_key, "audio/mpeg"
        )
        return {
            "token": token,
            "expires_at": expires_at,
            "provider": provider,
            "voice": resolved_voice,
        }
