from uuid import uuid4

from app.storybook_director import SoundStoryDirector


def test_tomato_story_assigns_one_generated_asset_to_every_sound_scene():
    recording_id = uuid4()
    segments = [
        {
            "id": uuid4(), "start_ms": index * 1000, "end_ms": (index + 1) * 1000,
            "text": text, "speaker_key": f"speaker_{index}", "speaker_name": speaker,
        }
        for index, (speaker, text) in enumerate([
            ("苗苗", "它说，下次请轻一点，我差点飞到奶奶家。"),
            ("妈妈", "哈哈哈哈，行了行了，你们俩先把桌子擦干净。"),
            ("爸爸", "收到。冠军事故现场，由本厨师负责处理。"),
        ])
    ]
    context = {
        "source_recording_id": recording_id,
        "title": "会飞的西红柿",
        "manifest": {"title": "会飞的西红柿"},
        "transcript_segments": segments,
    }

    result = SoundStoryDirector().compose(context)
    scenes = result["director_script"]["scenes"]

    assert len(scenes) == 7
    assert [scene["page_index"] for scene in scenes] == list(range(7))
    assert all(scene["asset_url"].endswith(".webp") for scene in scenes)
    assert scenes[3]["audio_sequence"][0]["kind"] == "original"
    assert scenes[3]["source_segment_id"] == str(segments[0]["id"])
