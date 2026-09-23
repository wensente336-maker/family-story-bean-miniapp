from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.io import wavfile
from scipy.spatial.distance import pdist

from .config import Settings
from .transcript_repository import PostgresTranscriptRepository
from .upload_storage import LocalObjectStorage


class AsrConfigurationError(RuntimeError):
    pass


def build_asr_prompt(settings: Settings, recording: dict | None = None) -> str:
    """Build a bounded vocabulary hint without turning it into transcript content."""

    recording = recording or {}
    terms: list[str] = []
    title = str(recording.get("title") or "").strip()
    if title:
        terms.append(title)
    for name in recording.get("family_member_names") or []:
        value = str(name or "").strip()
        if value and value not in terms:
            terms.append(value)
    base = settings.asr_initial_prompt.strip()
    if terms:
        base = f"{base} 可能出现的人物、节目或专有名词：{'、'.join(terms[:30])}。"
    return base[:500]


class AudioPreprocessor:
    def normalize(self, source: Path, destination: Path) -> None:
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            "-af", "highpass=f=60,lowpass=f=7800,loudnorm=I=-18:TP=-2:LRA=11",
            str(destination),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if completed.returncode != 0:
            raise RuntimeError(f"audio preprocessing failed: {completed.stderr[-300:]}")


class MlxWhisperProvider:
    name = "mlx_whisper"

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.asr_model_path:
            raise AsrConfigurationError("ASR_MODEL_PATH is not configured")
        self.model_path = Path(settings.asr_model_path).expanduser().resolve()
        if not self.model_path.exists():
            raise AsrConfigurationError("ASR model path does not exist")
        retry_path = settings.asr_retry_model_path.strip()
        self.retry_model_path = (
            Path(retry_path).expanduser().resolve() if retry_path else self.model_path
        )
        if settings.asr_retry_enabled and not self.retry_model_path.exists():
            raise AsrConfigurationError("ASR retry model path does not exist")

    @staticmethod
    def _normalize_segments(raw: dict) -> list[dict]:
        segments = []
        for item in raw.get("segments", []):
            text = str(item.get("text", "")).strip()
            start_ms = max(0, round(float(item.get("start", 0)) * 1000))
            end_ms = max(start_ms + 1, round(float(item.get("end", 0)) * 1000))
            words = []
            word_confidences = []
            for word in item.get("words", []):
                word_text = str(word.get("word", "")).strip()
                probability = float(word.get("probability", 0))
                word_start = max(start_ms, round(float(word.get("start", 0)) * 1000))
                word_end = max(word_start + 1, round(float(word.get("end", 0)) * 1000))
                if word_text:
                    words.append({
                        "text": word_text, "start_ms": word_start, "end_ms": word_end,
                        "confidence": round(max(0.0, min(1.0, probability)), 4),
                    })
                    word_confidences.append(probability)
            confidence = (
                sum(word_confidences) / len(word_confidences)
                if word_confidences else math.exp(float(item.get("avg_logprob", -10)))
            )
            no_speech = float(item.get("no_speech_prob", 0))
            if not text or end_ms <= start_ms:
                continue
            if no_speech > 0.6 and confidence < 0.35:
                continue
            segments.append({
                "speaker_key": "speaker_a",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
                "confidence": round(max(0.0, min(1.0, confidence)), 4),
                "words": words,
            })
        return segments

    def _retry_low_confidence_segments(
        self, mlx_whisper, audio_path: Path, segments: list[dict], initial_prompt: str,
    ) -> tuple[list[dict], int, int]:
        if not self.settings.asr_retry_enabled:
            return segments, 0, 0
        low_confidence = [
            segment for segment in segments
            if (
                segment["confidence"] < self.settings.asr_low_confidence_threshold
                or any(
                    word["confidence"] < self.settings.asr_low_confidence_threshold
                    for word in segment.get("words", [])
                )
            )
        ][:self.settings.asr_max_retry_segments]
        if not low_confidence:
            return segments, 0, 0
        clip_timestamps: list[float] = []
        for segment in low_confidence:
            clip_timestamps.extend([
                max(0.0, segment["start_ms"] / 1000 - 0.35),
                segment["end_ms"] / 1000 + 0.35,
            ])
        retried_raw = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=str(self.retry_model_path),
            language=self.settings.asr_language,
            word_timestamps=True,
            verbose=False,
            initial_prompt=initial_prompt or None,
            clip_timestamps=clip_timestamps,
            condition_on_previous_text=False,
            temperature=0.2,
            best_of=5,
        )
        retry_candidates = self._normalize_segments(retried_raw)
        selected_ids = {id(segment) for segment in low_confidence}
        result: list[dict] = []
        replaced_count = 0
        for segment in segments:
            if id(segment) not in selected_ids:
                result.append(segment)
                continue
            bounded = []
            for candidate in retry_candidates:
                start_ms = max(segment["start_ms"], candidate["start_ms"])
                end_ms = min(segment["end_ms"], candidate["end_ms"])
                if end_ms > start_ms:
                    bounded.append({**candidate, "start_ms": start_ms, "end_ms": end_ms})
            retry_confidence = (
                sum(item["confidence"] for item in bounded) / len(bounded)
                if bounded else 0.0
            )
            if bounded and retry_confidence > segment["confidence"]:
                result.extend(bounded)
                replaced_count += 1
            else:
                result.append(segment)
        return (
            sorted(result, key=lambda item: (item["start_ms"], item["end_ms"])),
            len(low_confidence),
            replaced_count,
        )

    def transcribe(self, audio_path: Path, initial_prompt: str = "") -> dict:
        import mlx_whisper

        raw = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=str(self.model_path),
            language=self.settings.asr_language,
            word_timestamps=True,
            verbose=False,
            initial_prompt=initial_prompt or None,
            condition_on_previous_text=True,
            hallucination_silence_threshold=1.0,
        )
        segments = self._normalize_segments(raw)
        segments, second_pass_attempted, second_pass_replaced = self._retry_low_confidence_segments(
            mlx_whisper, audio_path, segments, initial_prompt,
        )
        return {
            "provider": self.name,
            "model": self.model_path.name,
            "retry_model": self.retry_model_path.name,
            "second_pass_attempted_segments": second_pass_attempted,
            "second_pass_segments": second_pass_replaced,
            "language": raw.get("language", self.settings.asr_language),
            "segments": segments,
        }


class DemoFamilyConversationProvider:
    """Deterministic local-only transcript for the bundled family dinner demo.

    This provider keeps the MVP runnable without a multi-gigabyte Whisper model.
    It is selected explicitly with ``ASR_PROVIDER=demo`` and must not be used for
    real user recordings or production deployments.
    """

    name = "demo_family_conversation"
    model = "family-dinner-script-v1"
    utterances = (
        ("speaker_a", "都坐好啦，今天这锅汤是爸爸负责，大家先给他一点信心。"),
        ("speaker_b", "什么叫一点信心？我这可是祖传手艺。最后一颗西红柿，隆重下锅！"),
        ("speaker_c", "等一下！它弹出来了！爸爸，西红柿跑到你的杯子里了！"),
        ("speaker_b", "咳，我本来就是想做一杯……番茄拿铁。"),
        ("speaker_a", "你先别发明菜名，杯子里还是牛奶呢。"),
        ("speaker_c", "那它现在是游泳冠军！我给它颁奖，奖品是回到汤里。"),
        ("speaker_b", "请冠军发表获奖感言。"),
        ("speaker_c", "它说，下次请轻一点，我差点飞到奶奶家。"),
        ("speaker_a", "哈哈哈哈，行了行了，你们俩先把桌子擦干净。"),
        ("speaker_b", "收到。冠军事故现场，由本厨师负责处理。"),
        ("speaker_a", "今天最好吃的不一定是汤，最好记的一定是这颗会飞的西红柿。"),
        ("speaker_b", "同意。来，冠军回锅，咱们开饭。"),
        ("speaker_c", "等等！我要先给它拍一张冠军照！"),
    )

    def transcribe(self, audio_path: Path) -> dict:
        with wave.open(str(audio_path), "rb") as audio:
            duration_ms = max(1, round(audio.getnframes() / audio.getframerate() * 1000))
        gap_ms = min(250, max(0, duration_ms // 100))
        available_ms = max(len(self.utterances), duration_ms - gap_ms * (len(self.utterances) - 1))
        weights = [max(1, len(text)) for _, text in self.utterances]
        total_weight = sum(weights)
        cursor = 0
        segments = []
        for index, ((speaker_key, text), weight) in enumerate(zip(self.utterances, weights, strict=True)):
            if index == len(self.utterances) - 1:
                end_ms = duration_ms
            else:
                end_ms = min(duration_ms, cursor + max(1, round(available_ms * weight / total_weight)))
            segments.append({
                "speaker_key": speaker_key,
                "start_ms": cursor,
                "end_ms": max(cursor + 1, end_ms),
                "text": text,
                "confidence": 0.99,
                "words": [],
            })
            cursor = min(duration_ms - 1, end_ms + gap_ms)
        return {
            "provider": self.name,
            "model": self.model,
            "language": "zh",
            "segments": segments,
        }


def build_asr_provider(settings: Settings):
    if settings.asr_provider == "demo":
        if (
            not settings.allow_demo_asr
            or settings.app_env.lower() not in {"development", "test"}
        ):
            raise AsrConfigurationError(
                "demo ASR requires ALLOW_DEMO_ASR=true in development or test"
            )
        return DemoFamilyConversationProvider()
    if settings.asr_provider == "mlx_whisper":
        return MlxWhisperProvider(settings)
    raise AsrConfigurationError(
        f"unsupported ASR_PROVIDER: {settings.asr_provider}"
    )


class ConservativeSpeakerDiarizer:
    """Group utterances by coarse acoustics without inferring a real identity."""

    labels = ("speaker_a", "speaker_b", "speaker_c")

    @staticmethod
    def _features(samples: np.ndarray, sample_rate: int) -> np.ndarray:
        if len(samples) < sample_rate // 8:
            return np.zeros(6, dtype=np.float64)
        signal = samples.astype(np.float64)
        signal -= signal.mean()
        peak = np.max(np.abs(signal)) or 1.0
        signal /= peak
        windowed = signal * np.hanning(len(signal))
        spectrum = np.abs(np.fft.rfft(windowed)) + 1e-9
        frequencies = np.fft.rfftfreq(len(windowed), 1 / sample_rate)
        total = float(spectrum.sum())
        centroid = float((frequencies * spectrum).sum() / total) / 1000
        low = float(spectrum[(frequencies >= 80) & (frequencies < 300)].sum() / total)
        mid = float(spectrum[(frequencies >= 300) & (frequencies < 1200)].sum() / total)
        high = float(spectrum[(frequencies >= 1200) & (frequencies < 4000)].sum() / total)
        zcr = float(np.mean(np.abs(np.diff(np.signbit(signal)))))
        fft_size = 1 << (2 * len(signal) - 1).bit_length()
        spectrum_for_pitch = np.fft.rfft(signal, fft_size)
        autocorrelation = np.fft.irfft(
            spectrum_for_pitch * np.conjugate(spectrum_for_pitch), fft_size
        )[:len(signal)]
        min_lag = max(1, sample_rate // 400)
        max_lag = min(len(autocorrelation) - 1, sample_rate // 70)
        pitch = 0.0
        if max_lag > min_lag:
            lag = min_lag + int(np.argmax(autocorrelation[min_lag:max_lag]))
            strength = autocorrelation[lag] / (autocorrelation[0] + 1e-9)
            if strength > 0.12:
                pitch = math.log(max(70.0, min(400.0, sample_rate / lag)))
        return np.array([pitch, centroid, zcr * 10, low, mid, high], dtype=np.float64)

    def assign(self, audio_path: Path, segments: list[dict]) -> None:
        if len(segments) < 2:
            return
        sample_rate, samples = wavfile.read(audio_path)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        feature_rows = []
        for segment in segments:
            start = max(0, round(segment["start_ms"] * sample_rate / 1000))
            end = min(len(samples), round(segment["end_ms"] * sample_rate / 1000))
            feature_rows.append(self._features(samples[start:end], sample_rate))
        features = np.vstack(feature_rows)
        deviation = features.std(axis=0)
        useful = deviation > 1e-6
        if not useful.any():
            return
        normalized = (features[:, useful] - features[:, useful].mean(axis=0)) / deviation[useful]
        distances = pdist(normalized)
        if not np.isfinite(distances).all() or np.max(distances) < 1.35:
            return
        tree = linkage(distances, method="average")
        clusters = fcluster(tree, t=2.15, criterion="distance")
        if len(set(clusters)) > 3:
            clusters = fcluster(tree, t=3, criterion="maxclust")
        cluster_to_speaker: dict[int, str] = {}
        for segment, cluster in zip(segments, clusters, strict=True):
            cluster_id = int(cluster)
            if cluster_id not in cluster_to_speaker:
                cluster_to_speaker[cluster_id] = self.labels[len(cluster_to_speaker)]
            segment["speaker_key"] = cluster_to_speaker[cluster_id]


class RecordingTranscriptionPipeline:
    def __init__(
        self, settings: Settings, repository: PostgresTranscriptRepository,
        storage: LocalObjectStorage,
    ):
        self.settings = settings
        self.repository = repository
        self.storage = storage
        self.preprocessor = AudioPreprocessor()
        self.diarizer = ConservativeSpeakerDiarizer()

    def process(self, recording_id) -> dict:
        recording = self.repository.get_recording_internal(recording_id)
        if recording is None:
            raise ValueError("recording not found")
        provider = build_asr_provider(self.settings)
        source = self.storage.path_for(recording["object_key"])
        with tempfile.TemporaryDirectory(prefix="storybean-asr-") as directory:
            normalized = Path(directory) / "normalized.wav"
            self.preprocessor.normalize(source, normalized)
            prompt = build_asr_prompt(self.settings, recording)
            result = (
                provider.transcribe(normalized, initial_prompt=prompt)
                if provider.name == "mlx_whisper" else provider.transcribe(normalized)
            )
            if provider.name == "mlx_whisper":
                self.diarizer.assign(normalized, result["segments"])
        self.repository.replace_transcript(
            recording_id, result, self.settings.pipeline_version
        )
        return result
