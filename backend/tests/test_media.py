import hashlib
import subprocess
import struct
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.media import MediaValidationError, validate_audio, validate_media
from app.podcast_cover import SoundPostcardCoverProcessor


def write_wav(path: Path, seconds: int) -> str:
    sample_rate = 8000
    data_size = sample_rate * seconds
    header = (
        b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate, 1, 8)
        + b"data" + struct.pack("<I", data_size)
    )
    with path.open("wb") as stream:
        stream.write(header)
        stream.seek(44 + data_size - 1)
        stream.write(b"\x80")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("minutes", [5, 10, 15])
def test_accepts_five_ten_and_fifteen_minute_wav(tmp_path: Path, minutes: int) -> None:
    path = tmp_path / f"family-{minutes}.wav"
    digest = write_wav(path, minutes * 60)
    info = validate_audio(path, digest)
    assert info.media_type == "audio/wav"
    assert abs(info.duration_ms - minutes * 60_000) <= 2


def test_rejects_over_fifteen_minutes(tmp_path: Path) -> None:
    path = tmp_path / "too-long.wav"
    digest = write_wav(path, 15 * 60 + 1)
    with pytest.raises(MediaValidationError, match="15 分钟") as raised:
        validate_audio(path, digest)
    assert raised.value.code == "AUDIO_TOO_LONG"


@pytest.mark.parametrize("content", [b"", b"not really an mp3"])
def test_rejects_empty_or_forged_audio(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "forged.mp3"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    with pytest.raises(MediaValidationError):
        validate_audio(path, digest)


def test_fifty_legal_samples_have_full_validation_success(tmp_path: Path) -> None:
    path = tmp_path / "sample.wav"
    digest = write_wav(path, 1)
    accepted = sum(validate_audio(path, digest).duration_ms > 0 for _ in range(50))
    assert accepted == 50


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sample.wav"
    write_wav(path, 1)
    with pytest.raises(MediaValidationError) as raised:
        validate_audio(path, "0" * 64)
    assert raised.value.code == "AUDIO_CHECKSUM_MISMATCH"


@pytest.mark.parametrize(
    ("suffix", "arguments", "expected_type"),
    [
        ("mp3", ["-codec:a", "libmp3lame"], "audio/mpeg"),
        ("m4a", ["-codec:a", "aac"], "audio/mp4"),
        ("aac", ["-codec:a", "aac", "-f", "adts"], "audio/aac"),
    ],
)
def test_accepts_all_compressed_mvp_formats(
    tmp_path: Path, suffix: str, arguments: list[str], expected_type: str
) -> None:
    source = tmp_path / "source.wav"
    write_wav(source, 1)
    output = tmp_path / f"sample.{suffix}"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), *arguments, str(output)],
        check=True,
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert validate_audio(output, digest).media_type == expected_type


@pytest.mark.parametrize(("suffix", "expected_type"), [("mp4", "video/mp4"), ("webm", "video/webm")])
def test_accepts_video_and_detects_embedded_audio(
    tmp_path: Path, suffix: str, expected_type: str
) -> None:
    output = tmp_path / f"family.{suffix}"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=navy:s=160x120:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", str(output),
        ],
        check=True,
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert validate_media(output, digest).media_type == expected_type


def test_rejects_video_without_audio_track(tmp_path: Path) -> None:
    output = tmp_path / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=navy:s=160x120:d=1", output],
        check=True,
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(MediaValidationError) as raised:
        validate_media(output, digest)
    assert raised.value.code == "MEDIA_NO_AUDIO"


def test_sound_postcard_cover_is_three_by_four_and_strips_metadata() -> None:
    source = BytesIO()
    Image.new("RGB", (900, 600), "#e27c62").save(source, "JPEG", exif=b"Exif\x00\x00private")
    processed = SoundPostcardCoverProcessor().process(source.getvalue(), "image/jpeg", .7, .5)
    assert (processed.width, processed.height) == (1200, 1600)
    assert Image.open(BytesIO(processed.main)).size == (1200, 1600)
    assert Image.open(BytesIO(processed.thumbnail)).size == (360, 480)
    assert b"private" not in processed.main
