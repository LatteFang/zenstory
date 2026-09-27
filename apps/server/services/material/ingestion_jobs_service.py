"""
Ingestion jobs service - SQLModel version.
Handles IngestionJob tracking and status updates.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from config.datetime_utils import utcnow
from models.material_models import IngestionJob

DISPATCH_STALE_AFTER = timedelta(minutes=10)
PROCESSING_STALE_AFTER = timedelta(hours=2)

# stage_progress key holding the effective stage map recorded at flow start
# (keys: config.material_settings.STAGE_KEYS).
ENABLED_STAGES_KEY = "enabled_stages"


def _load_stage_progress(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


class IngestionJobsService:
    """Ingestion job tracking service using SQLModel patterns."""

    def create_job(
        self,
        session: Session,
        novel_id: int,
        total_chapters: int,
        status: str = "pending",
        source_path: str = "",
        correlation_id: str | None = None,
    ) -> IngestionJob:
        """Create a new ingestion job."""
        job = IngestionJob(
            novel_id=novel_id,
            total_chapters=total_chapters,
            status=status,
            source_path=source_path,
            correlation_id=correlation_id,
        )
        session.add(job)
        session.flush()
        return job

    def get_latest_by_novel(
        self, session: Session, novel_id: int
    ) -> IngestionJob | None:
        """Get the latest ingestion job for a novel."""
        statement = (
            select(IngestionJob)
            .where(IngestionJob.novel_id == novel_id)
            .order_by(IngestionJob.created_at.desc())
        )
        return session.exec(statement).first()

    def update_status(self, session: Session, job_id: int, status: str) -> None:
        """Update job status."""
        job = session.get(IngestionJob, job_id)
        if job:
            job.status = status
            if status == "processing" and job.started_at is None:
                job.started_at = utcnow()
            if status in {"completed", "completed_with_errors", "failed"}:
                job.completed_at = utcnow()
            job.updated_at = utcnow()
            session.add(job)
            session.flush()

    def update_processed(
        self,
        session: Session,
        job_id: int,
        processed_chapters: int | None = None,
        status: str | None = None,
        stage: str | None = None,
        stage_status: str | None = None,
        stage_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Update processed count, status, and optional stage/error metadata."""
        job = session.get(IngestionJob, job_id)
        if not job:
            return

        if processed_chapters is not None:
            normalized = max(0, processed_chapters)
            if job.total_chapters > 0:
                normalized = min(normalized, job.total_chapters)
            # Keep monotonic progress to avoid regressions on retries/resumes.
            job.processed_chapters = max(job.processed_chapters, normalized)

        if status is not None:
            job.status = status
            if status == "processing" and job.started_at is None:
                job.started_at = utcnow()
            if status in {"completed", "completed_with_errors", "failed"}:
                job.completed_at = utcnow()

        if stage:
            payload = stage_data or {}
            job.update_stage_progress(stage, stage_status or status or "processing", **payload)

        if error_message:
            job.error_message = error_message
        if error_details:
            job.error_details = json.dumps(error_details, ensure_ascii=False)

        job.updated_at = utcnow()
        session.add(job)
        session.flush()

    def update_stage_progress(
        self,
        session: Session,
        job_id: int,
        stage: str,
        status: str,
        **stage_payload: Any,
    ) -> None:
        """Update only stage progress payload for the job."""
        job = session.get(IngestionJob, job_id)
        if not job:
            return
        if status == "processing" and job.started_at is None:
            job.started_at = utcnow()
        job.update_stage_progress(stage, status, **stage_payload)
        job.updated_at = utcnow()
        session.add(job)
        session.flush()

    def set_enabled_stages(
        self,
        session: Session,
        job_id: int,
        enabled_stages: dict[str, bool],
    ) -> None:
        """Persist the stage map under stage_progress["enabled_stages"].

        Semantics: "stage may have produced data" for this novel. The new map is
        OR-merged with every earlier snapshot of the same novel (this job's own
        snapshot on resume, earlier jobs' snapshots on retry), so turning a stage
        off and resuming/retrying never hides data an earlier run produced.
        """
        job = session.get(IngestionJob, job_id)
        if not job:
            return
        merged = {k: bool(v) for k, v in enabled_stages.items()}
        novel_jobs = session.exec(
            select(IngestionJob).where(IngestionJob.novel_id == job.novel_id)
        ).all()
        for other in novel_jobs:
            previous = self.get_enabled_stages(other) or {}
            if "stories" in previous and "storylines" not in previous:
                # Older snapshots used "stories" for both 剧情 and 故事线.
                previous["storylines"] = previous["stories"]
            for key, value in previous.items():
                merged[key] = merged.get(key, False) or value
        progress = _load_stage_progress(job.stage_progress)
        progress[ENABLED_STAGES_KEY] = merged
        job.stage_progress = json.dumps(progress, ensure_ascii=False)
        job.updated_at = utcnow()
        session.add(job)
        session.flush()

    @staticmethod
    def get_enabled_stages(job: IngestionJob | None) -> dict[str, bool] | None:
        """Read the enabled-stage snapshot; None for jobs created before snapshots existed."""
        if job is None:
            return None
        snapshot = _load_stage_progress(job.stage_progress).get(ENABLED_STAGES_KEY)
        if not isinstance(snapshot, dict):
            return None
        return {str(k): bool(v) for k, v in snapshot.items()}

    def reconcile_stale_job(self, session: Session, job: IngestionJob) -> IngestionJob:
        """
        Best-effort reconciliation for stale pending/processing jobs.

        This provides a read-path safety net so obviously orphaned jobs do not
        stay visible forever as pending/processing.
        """
        now = utcnow()
        last_updated = job.updated_at or job.created_at or now
        if getattr(last_updated, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
            from datetime import UTC

            last_updated = last_updated.replace(tzinfo=UTC)

        age = now - last_updated

        if (
            job.status == "pending"
            and not job.correlation_id
            and age >= DISPATCH_STALE_AFTER
        ):
            self.update_processed(
                session,
                job.id,
                status="failed",
                stage="queue",
                stage_status="failed",
                stage_data={
                    "reconciled": True,
                    "reason": "dispatch_timeout",
                },
                error_message="拆解任务调度超时，请重试",
                error_details={
                    "stage": "dispatch_timeout",
                    "message": "Flow dispatch did not complete before timeout",
                },
            )
            session.commit()
            session.refresh(job)
            return job

        if job.status == "processing" and age >= PROCESSING_STALE_AFTER:
            self.update_processed(
                session,
                job.id,
                status="failed",
                stage="watchdog",
                stage_status="failed",
                stage_data={
                    "reconciled": True,
                    "reason": "processing_timeout",
                },
                error_message="拆解任务处理超时，请重试",
                error_details={
                    "stage": "processing_timeout",
                    "message": "Flow progress stalled beyond timeout",
                },
            )
            session.commit()
            session.refresh(job)
            return job

        return job
