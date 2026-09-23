from uuid import uuid4

from app.moment_discovery import ExplainableMomentRanker, MomentDiscoveryService


def segment(start, end, text, speaker="speaker_a", confidence=0.9):
    return {
        "id": uuid4(), "start_ms": start, "end_ms": end, "text": text,
        "speaker_key": speaker, "confidence": confidence,
    }


class MemoryMomentRepository:
    def __init__(self, segments, duration_ms=0):
        self.source = {
            "recording": {"scene_type": "周日晚餐", "transcript_revision": 3, "duration_ms": duration_ms},
            "segments": segments,
            "speaker_names": {
                "speaker_a": {"family_member_id": None, "display_name": "孩子"},
                "speaker_b": {"family_member_id": None, "display_name": "爸爸"},
            },
        }
        self.saved = []

    def load_source(self, _recording_id):
        return self.source

    def replace_moments(self, _recording_id, moments, _pipeline_version, _revision):
        self.saved = moments


def test_ranker_prefers_emotional_complete_family_exchange() -> None:
    segments = [
        segment(0, 3000, "今天吃饭。"),
        segment(4000, 7000, "爸爸把西红柿掉进汤里了！", "speaker_b"),
        segment(7100, 10000, "我们都笑了，太好玩了！"),
        segment(50000, 52000, "明天见。"),
    ]
    ranked = ExplainableMomentRanker().rank(segments)
    assert ranked[0].start_ms <= 4000
    assert ranked[0].breakdown["humor"] > 0
    assert ranked[0].breakdown["participation"] > 0.3


def test_storyboards_only_quote_source_transcript() -> None:
    segments = [
        segment(0, 2500, "妈妈，月亮是天空的夜灯吗？"),
        segment(2600, 5000, "是呀，它今晚陪我们回家。", "speaker_b"),
    ]
    repository = MemoryMomentRepository(segments)
    service = MomentDiscoveryService(repository, "storyboard-v1")
    service.process(uuid4())
    source_texts = {item["text"] for item in segments}
    assert repository.saved
    for moment in repository.saved:
        storyboard = moment["storyboard"]
        assert storyboard["highlight_quote"] in source_texts
        assert all(source["quote"] in source_texts for source in storyboard["source_segments"])
        assert all(source["transcript_segment_id"] for source in storyboard["source_segments"])


def test_same_input_produces_stable_rank_and_storyboard() -> None:
    segments = [
        segment(0, 2000, "第一次一起做蛋糕！"),
        segment(2100, 5000, "爸爸竟然把盐当成了糖。", "speaker_b"),
        segment(5100, 8000, "我们都笑了。"),
    ]
    first = MemoryMomentRepository(segments)
    second = MemoryMomentRepository(segments)
    MomentDiscoveryService(first, "storyboard-v1").process(uuid4())
    MomentDiscoveryService(second, "storyboard-v1").process(uuid4())
    assert first.saved == second.saved


def test_longer_recording_produces_more_than_three_candidates() -> None:
    segments = [
        segment(index * 60_000, index * 60_000 + 8_000, f"第{index}段家庭故事，大家都笑了！")
        for index in range(8)
    ]
    repository = MemoryMomentRepository(segments, duration_ms=9 * 60_000)
    MomentDiscoveryService(repository, "storyboard-v1").process(uuid4())
    assert len(repository.saved) == 7
