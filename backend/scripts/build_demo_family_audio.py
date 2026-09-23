"""Build a short multi-speaker family recording for local product testing."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.config import get_settings
from app.podcast_audio import VolcengineNarrationSynthesizer


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "samples/family-dinner-funny-multivoice-demo.mp3"

DIALOGUE = [
    ("mom", "都坐好啦，今天这锅汤是爸爸负责，大家先给他一点信心。", 0.42),
    ("dad", "什么叫一点信心？我这可是祖传手艺。最后一颗西红柿，隆重下锅！", 0.30),
    ("child", "等一下！它弹出来了！爸爸，西红柿跑到你的杯子里了！", 0.22),
    ("dad", "咳，我本来就是想做一杯……番茄拿铁。", 0.36),
    ("mom", "你先别发明菜名，杯子里还是牛奶呢。", 0.24),
    ("child", "那它现在是游泳冠军！我给它颁奖，奖品是回到汤里。", 0.26),
    ("dad", "请冠军发表获奖感言。", 0.22),
    ("child", "它说，下次请轻一点，我差点飞到奶奶家。", 0.20),
    ("mom", "哈哈哈哈，行了行了，你们俩先把桌子擦干净。", 0.32),
    ("dad", "收到。冠军事故现场，由本厨师负责处理。", 0.28),
    ("mom", "今天最好吃的不一定是汤，最好记的一定是这颗会飞的西红柿。", 0.32),
    ("dad", "同意。来，冠军回锅，咱们开饭。", 0.22),
    ("child", "等等！我要先给它拍一张冠军照！", 0.70),
]

ROLE_VOICES = {
    "child": {
        "name": "黑猫侦探社咪仔",
        "speaker": "zh_female_mizai_saturn_bigtts",
        "speech_rate": 4,
    },
    "mom": {
        "name": "鸡汤女",
        "speaker": "zh_female_jitangnv_saturn_bigtts",
        "speech_rate": -5,
    },
    "dad": {
        "name": "大壹",
        "speaker": "zh_male_dayi_saturn_bigtts",
        "speech_rate": -2,
    },
}


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True, text=True)


def main() -> None:
    settings = get_settings()
    if not VolcengineNarrationSynthesizer(settings).available:
        raise RuntimeError("Volcengine TTS is not configured")
    synthesizers = {
        role: VolcengineNarrationSynthesizer(settings.model_copy(update={
            "volcengine_tts_voice": voice["speaker"],
            "volcengine_tts_speech_rate": voice["speech_rate"],
        }))
        for role, voice in ROLE_VOICES.items()
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="storybean-family-demo-") as directory:
        root = Path(directory)
        rendered: list[Path] = []
        for index, (role, text, pause) in enumerate(DIALOGUE, start=1):
            speech = synthesizers[role].synthesize(text, root / f"speech-{index:02d}")
            segment = root / f"segment-{index:02d}.wav"
            run(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(speech.path),
                "-af", (
                    "aresample=48000,"
                    "highpass=f=90,lowpass=f=7600,"
                    "aecho=0.8:0.65:28:0.045,"
                    f"apad=pad_dur={pause}"
                ),
                "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(segment),
            )
            rendered.append(segment)

        concat_file = root / "dialogue.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in rendered), encoding="utf-8"
        )
        voice = root / "voice.wav"
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:a", "pcm_s16le", str(voice),
        )

        duration = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(voice),
            ],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        room_tone = root / "room.wav"
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.006:duration={duration}",
            "-af", "lowpass=f=1300,volume=0.18", "-ac", "1", "-ar", "48000", str(room_tone),
        )
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(voice), "-i", str(room_tone),
            "-filter_complex", (
                "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0,"
                "acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180,"
                "loudnorm=I=-17:TP=-2:LRA=8[out]"
            ),
            "-map", "[out]", "-ac", "1", "-ar", "48000", "-b:a", "128k", str(OUTPUT),
        )

    print({"output": str(OUTPUT), "voices": ROLE_VOICES})


if __name__ == "__main__":
    main()
