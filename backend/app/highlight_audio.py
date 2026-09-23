from __future__ import annotations

import subprocess
from pathlib import Path


class HighlightAudioError(RuntimeError):
    pass


class HighlightAudioClipper:
    def clip(self, source: Path, destination: Path, start_ms: int, end_ms: int) -> None:
        if not source.exists():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.preparing.mp3')
        try:
            subprocess.run([
                'ffmpeg','-hide_banner','-loglevel','error','-y',
                '-ss',f'{start_ms / 1000:.3f}','-t',f'{(end_ms-start_ms) / 1000:.3f}',
                '-i',str(source),'-vn','-ac','1','-ar','44100','-codec:a','libmp3lame','-b:a','128k',
                str(temporary),
            ], check=True, capture_output=True, text=True, timeout=120)
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise HighlightAudioError('empty highlight audio')
            temporary.replace(destination)
        except (OSError, subprocess.SubprocessError) as exc:
            temporary.unlink(missing_ok=True)
            raise HighlightAudioError('highlight audio clipping failed') from exc
