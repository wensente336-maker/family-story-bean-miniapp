from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from .config import Settings
from .upload_storage import LocalObjectStorage


class PodcastRenderError(RuntimeError):
    pass


class SpeechSynthesisError(PodcastRenderError):
    pass


@dataclass(frozen=True)
class SynthesizedSpeech:
    path: Path
    provider: str
    voice: str


class NarrationSynthesizer(Protocol):
    provider: str
    voice: str

    @property
    def available(self) -> bool: ...

    def synthesize(self, text: str, destination_stem: Path) -> SynthesizedSpeech: ...


class VolcengineNarrationSynthesizer:
    """Server-side Doubao TTS adapter using the HTTP V3 chunked endpoint."""

    provider = "volcengine-doubao"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.app_id = settings.volcengine_tts_app_id.strip()
        self.access_token = settings.volcengine_tts_access_token.strip()
        self.api_key = settings.volcengine_tts_api_key.strip()
        self.endpoint = settings.volcengine_tts_endpoint
        self.resource_id = settings.volcengine_tts_resource_id
        self.voice = settings.volcengine_tts_voice
        self.sample_rate = settings.volcengine_tts_sample_rate
        self.speech_rate = settings.volcengine_tts_speech_rate
        self.timeout = settings.volcengine_tts_timeout_seconds
        self.transport = transport

    @property
    def available(self) -> bool:
        return bool(self.api_key or (self.app_id and self.access_token))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": str(uuid4()),
            "X-Control-Require-Usage-Tokens-Return": "*",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        else:
            headers.update({
                "X-Api-App-Id": self.app_id,
                "X-Api-App-Key": self.app_id,
                "X-Api-Access-Key": self.access_token,
                "Authorization": f"Bearer;{self.access_token}",
            })
        return headers

    @staticmethod
    def _audio_from_lines(lines) -> bytes:
        audio = bytearray()
        finished = False
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SpeechSynthesisError("Doubao TTS returned an unreadable response") from exc
            code = int(event.get("code", -1))
            if code == 0 and event.get("data"):
                try:
                    audio.extend(base64.b64decode(event["data"], validate=True))
                except (ValueError, TypeError) as exc:
                    raise SpeechSynthesisError("Doubao TTS returned invalid audio data") from exc
            elif code == 20000000:
                finished = True
                break
            elif code != 0:
                message = str(event.get("message") or event.get("msg") or "unknown error")
                raise SpeechSynthesisError(f"Doubao TTS rejected the request ({code}): {message}")
        if not audio:
            suffix = " before completion" if not finished else ""
            raise SpeechSynthesisError(f"Doubao TTS returned no audio{suffix}")
        return bytes(audio)

    def synthesize(self, text: str, destination_stem: Path) -> SynthesizedSpeech:
        if not self.available:
            raise SpeechSynthesisError("Doubao TTS credentials are not configured")
        payload = {
            "user": {"uid": "family-story-bean"},
            "req_params": {
                "text": text,
                "speaker": self.voice,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": self.sample_rate,
                    "speech_rate": self.speech_rate,
                },
            },
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(self.timeout), transport=self.transport
                ) as client:
                    with client.stream(
                        "POST", self.endpoint, headers=self._headers(), json=payload
                    ) as response:
                        if response.status_code >= 400:
                            vendor_message = response.headers.get("X-Api-Message", "")
                            vendor_code = ""
                            try:
                                error_payload = json.loads(response.read())
                                error_header = error_payload.get("header", {})
                                vendor_code = str(error_header.get("code") or "")
                                vendor_message = str(
                                    error_header.get("message") or vendor_message
                                )
                            except (json.JSONDecodeError, TypeError, ValueError):
                                pass
                            code_detail = f" ({vendor_code})" if vendor_code else ""
                            detail = f": {vendor_message}" if vendor_message else ""
                            raise SpeechSynthesisError(
                                f"Doubao TTS HTTP {response.status_code}{code_detail}{detail}"
                            )
                        audio = self._audio_from_lines(response.iter_lines())
                destination = destination_stem.with_suffix(".mp3")
                destination.write_bytes(audio)
                return SynthesizedSpeech(destination, self.provider, self.voice)
            except (httpx.HTTPError, SpeechSynthesisError) as exc:
                last_error = exc
                retryable = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and (exc.response.status_code == 429 or exc.response.status_code >= 500)
                )
                if attempt < 2 and retryable:
                    time.sleep(0.2 * (2 ** attempt))
                else:
                    break
        raise SpeechSynthesisError(str(last_error) if last_error else "Doubao TTS failed")


class MacOsNarrationSynthesizer:
    provider = "macos-system-voice"
    voice = "Ting-Ting"

    @property
    def available(self) -> bool:
        return shutil.which("say") is not None

    def synthesize(self, text: str, destination_stem: Path) -> SynthesizedSpeech:
        if not self.available:
            raise SpeechSynthesisError("macOS system voice is unavailable")
        destination = destination_stem.with_suffix(".aiff")
        try:
            subprocess.run(
                ["say", "-v", self.voice, "-r", "175", "-o", str(destination), text],
                check=True, capture_output=True, text=True,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            raise SpeechSynthesisError("macOS system voice failed") from exc
        return SynthesizedSpeech(destination, self.provider, self.voice)


class LocalPodcastRenderer:
    """MVP renderer: pluggable natural TTS + traceable original audio + FFmpeg."""

    def __init__(
        self, settings: Settings, synthesizers: list[NarrationSynthesizer] | None = None
    ):
        self.settings = settings
        self.storage = LocalObjectStorage(settings)
        if synthesizers is not None:
            self.synthesizers = synthesizers
        else:
            configured: list[NarrationSynthesizer] = []
            provider = settings.podcast_tts_provider.strip().lower()
            if provider in {"auto", "volcengine", "doubao"}:
                doubao = VolcengineNarrationSynthesizer(settings)
                if doubao.available:
                    configured.append(doubao)
            if provider in {"auto", "local", "macos"} or settings.podcast_tts_fallback_to_system:
                configured.append(MacOsNarrationSynthesizer())
            self.synthesizers = configured

    @staticmethod
    def _run(*args: str) -> None:
        try:
            subprocess.run(args, check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            raise PodcastRenderError(str(exc)) from exc

    @staticmethod
    def _duration_ms(path: Path) -> int:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            check=True, capture_output=True, text=True,
        )
        return round(float(result.stdout.strip()) * 1000)

    def _synthesize_narration(
        self, text: str, root: Path, index: int, disabled: set[str]
    ) -> tuple[SynthesizedSpeech | None, bool]:
        fallback_used = False
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
        for position, synthesizer in enumerate(self.synthesizers):
            if synthesizer.provider in disabled or not synthesizer.available:
                continue
            try:
                speech = synthesizer.synthesize(
                    text, root / f"narration-{index:02d}-{text_hash}"
                )
                return speech, fallback_used or position > 0
            except SpeechSynthesisError:
                disabled.add(synthesizer.provider)
                fallback_used = True
        return None, fallback_used

    def render(
        self,
        source_object_key: str,
        destination_object_key: str,
        segments: list[dict],
        music_style: str = "warm-acoustic-light",
        _fallback_forced: bool = False,
    ) -> dict:
        source = self.storage.path_for(source_object_key)
        destination = self.storage.path_for(destination_object_key)
        if not source.exists():
            raise PodcastRenderError("source recording is missing")
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise PodcastRenderError("ffmpeg is unavailable")
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="storybean-podcast-") as temporary:
            root = Path(temporary)
            rendered: list[Path] = []
            providers: list[str] = []
            voices: list[str] = []
            narration_count = 0
            disabled_providers: set[str] = set()
            fallback_used = False
            timeline: list[dict] = []
            cursor_ms = 0
            expected_narrations = sum(
                1 for segment in segments if segment.get("kind") == "narration"
            )
            for index, segment in enumerate(segments, start=1):
                normalized = root / f"segment-{index:02d}.wav"
                if segment["kind"] == "narration":
                    speech, used_fallback = self._synthesize_narration(
                        segment["text"], root, index, disabled_providers
                    )
                    fallback_used = fallback_used or used_fallback
                    if speech is None:
                        continue
                    self._run(
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(speech.path), "-af",
                        "highpass=f=70,lowpass=f=11000,loudnorm=I=-18:TP=-2:LRA=8,apad=pad_dur=0.42",
                        "-ar", "48000", "-ac", "1", str(normalized),
                    )
                    providers.append(speech.provider)
                    voices.append(speech.voice)
                    narration_count += 1
                elif segment["kind"] == "original":
                    start = max(0, segment["start_ms"]) / 1000
                    duration = max(0.1, segment["end_ms"] - segment["start_ms"]) / 1000
                    self._run(
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
                        "-af", "highpass=f=80,lowpass=f=9000,loudnorm=I=-17:TP=-2:LRA=9,apad=pad_dur=0.45",
                        "-ar", "48000", "-ac", "1", str(normalized),
                    )
                else:
                    continue
                rendered.append(normalized)
                segment_duration_ms = self._duration_ms(normalized)
                timeline.append({
                    "segment_index": index,
                    "kind": segment["kind"],
                    "label": segment.get("label", ""),
                    "text": segment.get("text", ""),
                    "page_index": segment.get("page_index"),
                    "start_ms": cursor_ms,
                    "end_ms": cursor_ms + segment_duration_ms,
                    "source_segment_id": (
                        str(segment["source_segment_id"])
                        if segment.get("source_segment_id") else None
                    ),
                })
                cursor_ms += segment_duration_ms

            # A story should never contain a half-narrated voice track. If a
            # provider stops midway, rerender the whole episode as a coherent
            # original-only cut and keep that fallback explicit in metadata.
            if 0 < narration_count < expected_narrations:
                return LocalPodcastRenderer(self.settings, synthesizers=[]).render(
                    source_object_key,
                    destination_object_key,
                    segments,
                    music_style=music_style,
                    _fallback_forced=True,
                )

            if not rendered:
                raise PodcastRenderError("no podcast audio segment could be rendered")
            concat_list = root / "concat.txt"
            concat_list.write_text(
                "".join(f"file '{path.as_posix()}'\n" for path in rendered), encoding="utf-8"
            )
            voice_track = root / "voice.wav"
            self._run(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                "-safe", "0", "-i", str(concat_list), "-c:a", "pcm_s16le", str(voice_track),
            )
            duration_seconds = max(1.0, self._duration_ms(voice_track) / 1000)
            frequencies = {
                "warm-acoustic-light": (196, 294),
                "playful-ukulele-light": (262, 392),
                "gentle-piano-light": (174, 261),
                "minimal-documentary-light": (146, 220),
            }.get(music_style, (196, 294))
            self._run(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(voice_track),
                "-f", "lavfi", "-i", f"sine=frequency={frequencies[0]}:sample_rate=48000:duration={duration_seconds:.3f}",
                "-f", "lavfi", "-i", f"sine=frequency={frequencies[1]}:sample_rate=48000:duration={duration_seconds:.3f}",
                "-filter_complex",
                "[1:a]volume=0.025[m1];[2:a]volume=0.012[m2];"
                "[m1][m2]amix=inputs=2:normalize=0[bed];"
                "[bed][0:a]sidechaincompress=threshold=0.015:ratio=8:attack=20:release=350[ducked];"
                "[0:a][ducked]amix=inputs=2:duration=first:normalize=0,"
                "loudnorm=I=-16:TP=-1.5:LRA=8[out]",
                "-map", "[out]", "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "128k",
                str(destination),
            )
        unique_providers = list(dict.fromkeys(providers))
        unique_voices = list(dict.fromkeys(voices))
        return {
            "duration_ms": self._duration_ms(destination),
            "render_mode": "narrated" if narration_count else "original_only",
            "tts_provider": "+".join(unique_providers) if unique_providers else None,
            "tts_voice": "+".join(unique_voices) if unique_voices else None,
            "tts_quality": (
                "neural-natural" if "volcengine-doubao" in unique_providers
                else "system-basic" if unique_providers else None
            ),
            "tts_fallback_used": fallback_used or _fallback_forced,
            "narration_segments": narration_count,
            "voice_clone": False,
            "music_source": f"generated-owned-{music_style}",
            "music_style": music_style,
            "ducking_enabled": True,
            "timeline": timeline,
        }
