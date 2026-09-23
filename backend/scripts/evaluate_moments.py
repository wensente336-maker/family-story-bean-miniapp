from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.moment_discovery import ExplainableMomentRanker, StoryboardBuilder


FILLERS = [
    "今天天气不错。", "我们先吃饭吧。", "明天还要早起。", "好的，我知道了。",
]
HIGHLIGHTS = [
    ("欢乐", "爸爸竟然把盐当成糖，我们都笑了！"),
    ("温暖", "奶奶说最开心的事就是每周都能陪我们吃饭。"),
    ("成长", "这是我第一次自己系好鞋带，真的太开心了！"),
    ("童言", "月亮是不是天空忘记关掉的夜灯？"),
    ("回忆", "我还记得你小时候第一次叫我奶奶。"),
]


def build_recording(family_index: int, recording_index: int):
    category, highlight = HIGHLIGHTS[recording_index % len(HIGHLIGHTS)]
    gold_index = (family_index + recording_index) % 5
    texts = FILLERS.copy()
    texts.insert(gold_index, highlight)
    segments = []
    for index, text in enumerate(texts):
        start = index * 5000
        segments.append({
            "id": uuid5(NAMESPACE_URL, f"family-{family_index}-recording-{recording_index}-{index}"),
            "start_ms": start, "end_ms": start + 3600, "text": text,
            "speaker_key": f"speaker_{'ab'[index % 2]}", "confidence": 0.93,
        })
    return category, segments, segments[gold_index]["id"]


def evaluate() -> dict:
    ranker = ExplainableMomentRanker()
    builder = StoryboardBuilder()
    started = time.perf_counter()
    results = []
    total_quotes = 0
    traceable_quotes = 0
    fabricated_quotes = 0
    stable = True
    for family_index in range(10):
        for recording_index in range(5):
            category, segments, gold_id = build_recording(family_index, recording_index)
            ranked = ranker.rank(segments)
            reranked = ranker.rank(segments)
            stable = stable and [item.start_ms for item in ranked] == [item.start_ms for item in reranked]
            top_ids = {
                item["id"] for candidate in ranked for item in candidate.segments
            }
            source_texts = {item["text"] for item in segments}
            storyboards = []
            for candidate in ranked:
                board = builder.build(
                    {"scene_type": "家庭对话"}, candidate,
                    {"speaker_a": {"display_name": "家人 A"}, "speaker_b": {"display_name": "家人 B"}},
                    "storyboard-v1",
                )
                board.pop("_theme")
                storyboards.append(board)
                quotes = [source["quote"] for source in board["source_segments"]]
                if board["highlight_quote"]:
                    quotes.append(board["highlight_quote"])
                total_quotes += len(quotes)
                traceable_quotes += sum(quote in source_texts for quote in quotes)
                fabricated_quotes += sum(quote not in source_texts for quote in quotes)
            results.append({
                "family": family_index + 1, "recording": recording_index + 1,
                "category": category, "top3_hit": gold_id in top_ids,
                "moments": len(ranked),
            })
    hits = sum(item["top3_hit"] for item in results)
    return {
        "dataset": "synthetic-family-highlight-v1",
        "families": 10, "recordings": 50,
        "gold_origin": "synthetic scenario labels; not human double annotation",
        "top3_hits": hits, "top3_hit_rate": hits / len(results),
        "direct_quotes": total_quotes,
        "traceable_quotes": traceable_quotes,
        "traceability_rate": traceable_quotes / total_quotes if total_quotes else 1,
        "fabricated_quotes": fabricated_quotes,
        "stable_same_input": stable,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "families", "recordings", "top3_hit_rate", "traceability_rate",
        "fabricated_quotes", "stable_same_input", "elapsed_seconds",
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
