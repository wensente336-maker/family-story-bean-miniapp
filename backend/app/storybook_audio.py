from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .upload_storage import LocalObjectStorage


class StorybookAudioRenderError(RuntimeError):
    pass


class StorybookAudioRenderer:
    def __init__(self, storage: LocalObjectStorage):
        self.storage = storage

    @staticmethod
    def _run(*command: str) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
            raise StorybookAudioRenderError("无法生成书页原声音频") from exc

    @classmethod
    def _duration_ms(cls, path: Path) -> int:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            return max(1, round(float(result.stdout.strip()) * 1000))
        except (subprocess.CalledProcessError, OSError, ValueError) as exc:
            raise StorybookAudioRenderError("无法读取书页原声音频") from exc

    def render_clip(
        self,
        source_object_key: str,
        destination_object_key: str,
        start_ms: int,
        end_ms: int,
    ) -> int:
        source = self.storage.path_for(source_object_key)
        destination = self.storage.path_for(destination_object_key)
        if not source.exists():
            raise StorybookAudioRenderError("家庭原始录音已不可用")
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise StorybookAudioRenderError("本地音频工具不可用")
        if start_ms < 0 or end_ms <= start_ms or end_ms - start_ms > 60_000:
            raise StorybookAudioRenderError("家庭原声时间范围无效")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.stem}.rendering.mp3")
        try:
            self._run(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{start_ms / 1000:.3f}",
                "-t", f"{(end_ms - start_ms) / 1000:.3f}",
                "-i", str(source),
                "-vn", "-af", "highpass=f=70,lowpass=f=10000,loudnorm=I=-17:TP=-2:LRA=9",
                "-ar", "48000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "112k",
                str(temporary),
            )
            duration_ms = self._duration_ms(temporary)
            temporary.replace(destination)
            return duration_ms
        finally:
            temporary.unlink(missing_ok=True)
