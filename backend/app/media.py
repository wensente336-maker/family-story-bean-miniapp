from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MediaInfo:
    media_type: str
    duration_ms: int
    file_size: int
    sha256: str


FORMAT_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
}


def validate_media(path: Path, expected_sha256: str, max_duration_ms: int = 900000) -> MediaInfo:
    if not path.exists() or path.stat().st_size == 0:
        raise MediaValidationError("AUDIO_EMPTY", "音频文件为空")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if not hmac.compare_digest(digest, expected_sha256):
        raise MediaValidationError("AUDIO_CHECKSUM_MISMATCH", "音频摘要不一致")
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=format_name,duration:stream=codec_type",
                "-of", "json", str(path),
            ],
            check=True, capture_output=True, text=True, timeout=20,
        )
        data = json.loads(result.stdout)["format"]
        format_name = data["format_name"]
        duration_ms = round(float(data["duration"]) * 1000)
        stream_types = {
            stream.get("codec_type") for stream in json.loads(result.stdout).get("streams", [])
        }
    except (subprocess.SubprocessError, OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise MediaValidationError("AUDIO_CORRUPT", "无法读取音频内容") from exc
    if "audio" not in stream_types:
        raise MediaValidationError("MEDIA_NO_AUDIO", "媒体文件中没有可识别的音轨")
    if format_name in {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"}:
        media_type = "video/mp4" if "video" in stream_types else "audio/mp4"
    elif format_name in {"matroska,webm", "webm"}:
        media_type = "video/webm" if "video" in stream_types else "audio/webm"
    else:
        media_type = FORMAT_MEDIA_TYPES.get(format_name)
    if media_type is None:
        raise MediaValidationError(
            "AUDIO_FORMAT_UNSUPPORTED", "仅支持 MP3、M4A、WAV、AAC、MP4、MOV、WebM"
        )
    if duration_ms <= 0:
        raise MediaValidationError("AUDIO_CORRUPT", "音频时长无效")
    if duration_ms > max_duration_ms:
        raise MediaValidationError("AUDIO_TOO_LONG", "音频不能超过 15 分钟")
    return MediaInfo(media_type, duration_ms, path.stat().st_size, digest)


def validate_audio(path: Path, expected_sha256: str, max_duration_ms: int = 900000) -> MediaInfo:
    """Backward-compatible alias for callers that still submit audio-only media."""
    return validate_media(path, expected_sha256, max_duration_ms)
