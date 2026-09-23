"""Build a reproducible, privacy-safe ASR smoke set with macOS system voices."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


PHRASES = [
    "今天晚饭最好笑的事情是什么？",
    "爸爸把西红柿掉进了汤里，我们都笑了。",
    "我还记得你小时候也这样。",
    "周末我们一起去公园放风筝吧。",
    "这是今天最值得记住的家庭故事。",
]
VOICES = ["Tingting", "Meijia", "Sinji"]


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    bases: list[Path] = []

    for index in range(14):
        voice = VOICES[index % len(VOICES)]
        phrase = PHRASES[index % len(PHRASES)]
        aiff = output / f"source-{index:02d}.aiff"
        wav = output / f"speech-{index:02d}.wav"
        run("say", "-v", voice, "-r", str(155 + index % 4 * 15), "-o", str(aiff), phrase)
        audio_filter = "asetrate=22050*1.12,aresample=16000" if index in (3, 8, 13) else "aresample=16000"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff),
            "-af", audio_filter, "-ac", "1", str(wav))
        bases.append(wav)
        manifest.append({
            "id": f"speech-{index:02d}", "file": wav.name, "expect_speech": True,
            "category": "child_pitch" if index in (3, 8, 13) else "adult_clean",
        })

    for index in range(4):
        wav = output / f"noise-{index:02d}.wav"
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(bases[index]),
            "-f", "lavfi", "-i", f"anoisesrc=d=8:c=pink:r=16000:a={0.012 + index * 0.004}:s={100 + index}",
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[out]",
            "-map", "[out]", "-ac", "1", "-ar", "16000", str(wav),
        )
        manifest.append({
            "id": f"noise-{index:02d}", "file": wav.name, "expect_speech": True,
            "category": "background_noise",
        })

    overlap = output / "overlap.wav"
    run(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(bases[1]),
        "-i", str(bases[2]), "-filter_complex",
        "[1:a]adelay=700|700[b];[0:a][b]amix=inputs=2:duration=longest:normalize=1[out]",
        "-map", "[out]", "-ac", "1", "-ar", "16000", str(overlap),
    )
    manifest.append({"id": "overlap", "file": overlap.name, "expect_speech": True, "category": "overlap"})

    silence = output / "silence.wav"
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "anullsrc=r=16000:cl=mono", "-t", "4", str(silence))
    manifest.append({"id": "silence", "file": silence.name, "expect_speech": False, "category": "no_speech"})

    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output / "manifest.json")


if __name__ == "__main__":
    main()
