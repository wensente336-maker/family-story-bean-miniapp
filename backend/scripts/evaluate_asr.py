"""Evaluate processing success and timestamp invariants for an ASR fixture set."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from app.config import get_settings
from app.transcription import AudioPreprocessor, ConservativeSpeakerDiarizer, MlxWhisperProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture_dir = args.fixture_dir.resolve()
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    provider = MlxWhisperProvider(get_settings())
    preprocessor = AudioPreprocessor()
    diarizer = ConservativeSpeakerDiarizer()
    results = []

    with tempfile.TemporaryDirectory(prefix="storybean-asr-eval-") as directory:
        normalized_root = Path(directory)
        for item in manifest:
            started = time.perf_counter()
            try:
                normalized = normalized_root / item["file"]
                preprocessor.normalize(fixture_dir / item["file"], normalized)
                transcript = provider.transcribe(normalized)
                segments = transcript["segments"]
                diarizer.assign(normalized, segments)
                timestamps_valid = all(
                    0 <= segment["start_ms"] < segment["end_ms"] for segment in segments
                )
                passed = timestamps_valid and bool(segments) == bool(item["expect_speech"])
                error = None
            except Exception as exc:
                segments = []
                passed = False
                error = str(exc)[:300]
            results.append({
                **item, "passed": passed, "segments": len(segments),
                "elapsed_seconds": round(time.perf_counter() - started, 3), "error": error,
            })
            print(f"{item['id']}: {'PASS' if passed else 'FAIL'} ({len(segments)} segments)")

    passed_count = sum(result["passed"] for result in results)
    report = {
        "provider": provider.name, "model": provider.model_path.name,
        "samples": len(results), "passed": passed_count,
        "success_rate": round(passed_count / len(results), 4), "results": results,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
