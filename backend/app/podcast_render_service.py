from __future__ import annotations

from uuid import UUID, uuid4

from .podcast_audio import LocalPodcastRenderer, PodcastRenderError
from .podcast_render_repository import PodcastRenderRepository


class PodcastRenderService:
    def __init__(
        self,
        repository: PodcastRenderRepository,
        renderer: LocalPodcastRenderer,
    ):
        self.repository = repository
        self.renderer = renderer

    def run(self, job_id: UUID) -> dict:
        execution_token = f"podcast-render-{uuid4()}"
        job = self.repository.claim(job_id, execution_token)
        if job is None:
            return {"job_id": str(job_id), "status": "DUPLICATE_SKIPPED"}
        try:
            context = self.repository.load_context(job_id)
            if context is None:
                raise PodcastRenderError("已确认的播客策划不存在")
            if not context.get("source_object_key"):
                raise PodcastRenderError("家庭原始录音不存在")
            self.repository.update_progress(job_id, execution_token, 18)
            by_id = {str(item["id"]): item for item in context["materials"]}
            render_segments: list[dict] = []
            for item in context["plan"]["segments"]:
                segment = {
                    "kind": item["kind"],
                    "label": item["label"],
                    "text": item["text"],
                }
                if item["kind"] == "original":
                    source_ids = item.get("source_material_ids") or []
                    source = by_id.get(str(source_ids[0])) if source_ids else None
                    if source is None or item["text"] != source["confirmed_text"]:
                        raise PodcastRenderError("家庭原声来源校验失败")
                    segment.update({
                        "source_segment_id": source["source_segment_id"],
                        "start_ms": source["start_ms"],
                        "end_ms": source["end_ms"],
                    })
                render_segments.append(segment)
            self.repository.update_progress(job_id, execution_token, 35)
            destination_key = (
                f"families/{context['family_id']}/recordings/{context['recording_id']}"
                f"/podcasts/{context['podcast_version_id']}/v{context['version']}.mp3"
            )
            metadata = self.renderer.render(
                context["source_object_key"], destination_key, render_segments,
                music_style=context["music_style"] or "warm-acoustic-light",
            )
            metadata.update({
                "plan_revision": context["plan_revision"],
                "original_audio_traceable": True,
                "narrator_is_ai": True,
                "source_material_count": len(context["materials"]),
            })
            self.repository.update_progress(job_id, execution_token, 92)
            completed = self.repository.complete(
                job_id, execution_token, destination_key, metadata
            )
            if completed is None:
                raise PodcastRenderError("播客生成任务租约已失效")
            return completed
        except Exception as exc:
            self.repository.fail(
                job_id, execution_token, "PODCAST_RENDER_FAILED", str(exc)
            )
            return {"job_id": str(job_id), "status": "FAILED", "error": str(exc)}

