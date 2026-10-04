from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlmodel import Session

from models.material_models import IngestionJob, Novel, ProcessCheckpoint
from services.material.checkpoint_service import CheckpointService


def _novel(session: Session) -> Novel:
    novel = Novel(user_id="checkpoint-review-user", title="Checkpoint Novel")
    session.add(novel)
    session.flush()
    return novel


def _job(session: Session, novel: Novel, *, year: int, status: str) -> IngestionJob:
    job = IngestionJob(
        novel_id=novel.id, source_path="checkpoint.txt", status=status,
        created_at=datetime(year, 1, 1),
    )
    session.add(job)
    session.flush()
    return job


def _checkpoint(session: Session, novel: Novel, job: IngestionJob | None, *, year: int) -> ProcessCheckpoint:
    cp = ProcessCheckpoint(
        novel_id=novel.id, job_id=job.id if job else None, stage="stage1",
        stage_status="failed", checkpoint_data=json.dumps({"completed_chapter_ids": [1], "failed_chapter_ids": [2]}),
        created_at=datetime(year, 1, 1), updated_at=datetime(year, 1, 1),
    )
    session.add(cp)
    session.flush()
    return cp


@pytest.mark.parametrize("legacy_null", [False, True])
def test_retry_inherits_readonly_and_writes_current_job_copy(db_session, legacy_null):
    novel = _novel(db_session)
    previous = _job(db_session, novel, year=2020, status="failed")
    current = _job(db_session, novel, year=2022, status="pending")
    source = _checkpoint(db_session, novel, None if legacy_null else previous, year=2021)
    original = (source.job_id, source.stage_status, source.checkpoint_data)
    service = CheckpointService()

    inherited = service.get(db_session, novel.id, "stage1", job_id=current.id)
    assert inherited.id == source.id
    assert service.get_latest(db_session, novel.id, job_id=current.id).id == source.id
    result = service.upsert(
        db_session, novel.id, "stage1", {"failed_chapter_ids": []},
        status="processing", job_id=current.id,
    )
    assert result.id != source.id
    assert result.job_id == current.id
    assert json.loads(result.checkpoint_data) == {"completed_chapter_ids": [1], "failed_chapter_ids": []}
    assert (source.job_id, source.stage_status, source.checkpoint_data) == original
    assert service.get(db_session, novel.id, "stage1", job_id=current.id).id == result.id
    assert service.get_latest(db_session, novel.id, job_id=current.id).id == result.id


def test_current_job_wins_and_other_running_or_newer_jobs_are_not_seeds(db_session):
    novel = _novel(db_session)
    previous = _job(db_session, novel, year=2019, status="completed_with_errors")
    running = _job(db_session, novel, year=2020, status="processing")
    current = _job(db_session, novel, year=2022, status="pending")
    newer = _job(db_session, novel, year=2023, status="failed")
    valid = _checkpoint(db_session, novel, previous, year=2020)
    _checkpoint(db_session, novel, running, year=2021)
    _checkpoint(db_session, novel, newer, year=2024)
    service = CheckpointService()
    assert service.get(db_session, novel.id, "stage1", job_id=current.id).id == valid.id

    own = _checkpoint(db_session, novel, current, year=2022)
    assert service.get(db_session, novel.id, "stage1", job_id=current.id).id == own.id
    assert service.get_latest(db_session, novel.id, job_id=current.id).id == own.id


def test_scoped_checkpoint_rejects_job_from_another_novel(db_session):
    novel = _novel(db_session)
    other = _novel(db_session)
    wrong = _job(db_session, other, year=2022, status="pending")
    service = CheckpointService()
    with pytest.raises(ValueError, match="job"):
        service.upsert(db_session, novel.id, "stage1", {}, job_id=wrong.id)


def test_legacy_unscoped_reads_keep_creation_order(db_session):
    novel = _novel(db_session)
    older = _checkpoint(db_session, novel, None, year=2020)
    newer = _checkpoint(db_session, novel, None, year=2022)
    older.updated_at = datetime(2024, 1, 1)
    db_session.add(older)
    db_session.flush()
    service = CheckpointService()

    assert service.get(db_session, novel.id, "stage1").id == newer.id
    assert service.get_latest(db_session, novel.id).id == newer.id
