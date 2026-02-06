from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import httpx

from gateway.app import config
from gateway.app.domain.apollo_avatar import (
    ApolloAvatarRequest,
    GenArtifacts,
    SegmentArtifact,
    SegmentPlan,
    SegmentSpec,
)
from gateway.app.providers.video_gen_registry import get_video_gen_provider
from gateway.app.services.artifact_storage import get_download_url, upload_task_artifact
from gateway.app.utils.ffmpeg_concat import ffmpeg_concat_videos
from gateway.app.core.workspace import task_base_dir


class ApolloAvatarService:
    def __init__(self, *, repo, storage=None):
        self.repo = repo
        self.storage = storage

    def _build_plan(self, target_duration_sec: int, seed: Optional[int]) -> SegmentPlan:
        if target_duration_sec == 15:
            seg = 5
        elif target_duration_sec == 30:
            seg = 10
        else:
            raise ValueError("target_duration_sec must be 15 or 30")

        segments: list[SegmentSpec] = []
        for i in range(3):
            seed_i = None if seed is None else int(seed) + i
            segments.append(SegmentSpec(idx=i + 1, duration_sec=seg, seed=seed_i))

        return SegmentPlan(
            target_duration_sec=target_duration_sec,
            segment_duration_sec=seg,
            segment_count=3,
            segments=segments,
        )

    async def _download_to_path(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)

    async def generate_stitch_only(
        self,
        task: dict,
        req: ApolloAvatarRequest,
        *,
        live_enabled: bool,
    ) -> GenArtifacts:
        provider_name = getattr(config.settings, "apollo_avatar_provider", "fal_wan26_flash")
        plan = self._build_plan(req.target_duration_sec, req.seed)
        artifacts = GenArtifacts(provider=provider_name, plan=plan)

        task_id = str(task.get("task_id") or task.get("id") or "")
        task_dir = task_base_dir(task_id) / "apollo_avatar"
        seg_dir = task_dir / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)

        if not live_enabled:
            demo_base = getattr(config.settings, "demo_asset_base_url", "").rstrip("/")
            if demo_base:
                artifacts.final_video_url = f"{demo_base}/demo_{req.target_duration_sec}.mp4"
            return artifacts
        if not getattr(config.settings, "apollo_avatar_live_enabled", False):
            raise RuntimeError("Live gate disabled")

        provider = get_video_gen_provider()

        seg_paths: list[Path] = []
        for seg in plan.segments:
            res = await provider.generate_segment(
                avatar_image_url=req.avatar_image_url,
                ref_video_url=req.reference_video_url or "",
                prompt=req.prompt,
                duration_sec=seg.duration_sec,
                seed=seg.seed,
            )
            seg_path = seg_dir / f"seg_{seg.idx:02d}.mp4"
            await self._download_to_path(res.url, seg_path)
            seg_key = upload_task_artifact(
                task,
                seg_path,
                f"apollo_avatar/seg_{seg.idx:02d}.mp4",
                task_id=task_id,
            )
            seg_url = get_download_url(task_id, f"apollo_avatar/seg_{seg.idx:02d}.mp4")
            seg_paths.append(seg_path)
            artifacts.segments.append(
                SegmentArtifact(
                    idx=seg.idx,
                    duration_sec=seg.duration_sec,
                    video_url=seg_url,
                    request_id=res.meta.get("request_id") or "fal-unknown",
                    seed_used=seg.seed,
                )
            )

        final_path = task_dir / f"final_{req.target_duration_sec}.mp4"
        ffmpeg_concat_videos(seg_paths, final_path)
        upload_task_artifact(task, final_path, f"apollo_avatar/final_{req.target_duration_sec}.mp4", task_id=task_id)
        artifacts.final_video_url = get_download_url(task_id, f"apollo_avatar/final_{req.target_duration_sec}.mp4")

        manifest_path = task_dir / "segment_manifest.json"
        manifest_path.write_text(
            json.dumps(artifacts.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        upload_task_artifact(task, manifest_path, "apollo_avatar/manifest.json", task_id=task_id)
        artifacts.manifest_url = get_download_url(task_id, "apollo_avatar/manifest.json")

        return artifacts
