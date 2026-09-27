"""
Materials API exposes the per-job enabled-stage snapshot
(IngestionJob.stage_progress["enabled_stages"]) on list and detail responses.
"""
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from services.material.ingestion_jobs_service import IngestionJobsService
from tests.test_api.test_materials import (
    create_test_job,
    create_test_novel,
    create_test_user,
)

_SNAPSHOT = {
    "chapter_summaries": True,
    "plots": False,
    "characters": True,
    "meta": True,
    "synopsis": True,
    "stories": False,
    "storylines": False,
    "relationships": False,
}


@pytest.mark.integration
async def test_snapshot_persisted_and_exposed_on_detail_and_list(client: AsyncClient, db_session):
    user, token = await create_test_user(client, db_session, "stagesuser1")
    novel = create_test_novel(db_session, user.id, "Snapshot Novel")
    job = create_test_job(db_session, novel.id, "completed")
    job.update_stage_progress("stage1", "completed", summaries_count=3)
    db_session.add(job)
    db_session.commit()

    svc = IngestionJobsService()
    svc.set_enabled_stages(db_session, job.id, _SNAPSHOT)
    # Later stage updates must not drop the snapshot.
    svc.update_processed(db_session, job.id, stage="completed", stage_status="completed", stage_data={})
    db_session.commit()

    progress = json.loads(job.stage_progress)
    assert progress["enabled_stages"] == _SNAPSHOT
    assert progress["stage1"]["summaries_count"] == 3

    headers = {"Authorization": f"Bearer {token}"}
    detail = await client.get(f"/api/v1/materials/{novel.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["enabled_stages"] == _SNAPSHOT

    listing = await client.get("/api/v1/materials/list", headers=headers)
    assert listing.status_code == 200
    item = next(i for i in listing.json() if i["id"] == novel.id)
    assert item["enabled_stages"] == _SNAPSHOT


@pytest.mark.integration
async def test_old_jobs_without_snapshot_return_null(client: AsyncClient, db_session):
    user, token = await create_test_user(client, db_session, "stagesuser2")
    novel = create_test_novel(db_session, user.id, "Legacy Novel")
    job = create_test_job(db_session, novel.id, "completed")
    job.update_stage_progress("stage1", "completed")
    db_session.add(job)
    db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    detail = await client.get(f"/api/v1/materials/{novel.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["enabled_stages"] is None

    listing = await client.get("/api/v1/materials/list", headers=headers)
    item = next(i for i in listing.json() if i["id"] == novel.id)
    assert item["enabled_stages"] is None


def test_get_enabled_stages_handles_missing_and_malformed_progress():
    from models.material_models import IngestionJob

    assert IngestionJobsService.get_enabled_stages(None) is None
    assert IngestionJobsService.get_enabled_stages(IngestionJob(novel_id=1, source_path="x")) is None
    assert (
        IngestionJobsService.get_enabled_stages(
            IngestionJob(novel_id=1, source_path="x", stage_progress="not-json")
        )
        is None
    )
    assert (
        IngestionJobsService.get_enabled_stages(
            IngestionJob(novel_id=1, source_path="x", stage_progress=json.dumps({"enabled_stages": "bad"}))
        )
        is None
    )


@pytest.mark.integration
def test_set_enabled_stages_merges_previous_snapshots_on_resume_and_retry(db_session):
    """Snapshot means "stage may have produced data": resume/retry OR-merges earlier snapshots."""
    from datetime import timedelta

    from models.material_models import Novel

    novel = Novel(user_id="user-merge", title="Merge Novel")
    db_session.add(novel)
    db_session.commit()
    svc = IngestionJobsService()

    first = svc.create_job(db_session, novel.id, total_chapters=1, status="failed")
    produced = {**_SNAPSHOT, "plots": True, "stories": True, "storylines": True}
    svc.set_enabled_stages(db_session, first.id, produced)
    db_session.commit()

    # Resume of the same job after plots/stories were switched off.
    svc.set_enabled_stages(db_session, first.id, _SNAPSHOT)
    db_session.commit()
    assert IngestionJobsService.get_enabled_stages(first) == produced

    # Retry creates a new job: earlier jobs' snapshots still count.
    retry = svc.create_job(db_session, novel.id, total_chapters=1, status="pending")
    retry.created_at = first.created_at + timedelta(seconds=1)
    db_session.add(retry)
    db_session.commit()
    svc.set_enabled_stages(db_session, retry.id, {**_SNAPSHOT, "relationships": True})
    db_session.commit()
    assert IngestionJobsService.get_enabled_stages(retry) == {**produced, "relationships": True}


@pytest.mark.integration
def test_set_enabled_stages_merges_legacy_snapshot_without_storylines_key(db_session):
    from models.material_models import IngestionJob, Novel

    novel = Novel(user_id="user-merge2", title="Legacy Snapshot")
    db_session.add(novel)
    db_session.commit()
    legacy_snapshot = {k: v for k, v in _SNAPSHOT.items() if k != "storylines"}
    old = IngestionJob(
        novel_id=novel.id,
        source_path="x",
        status="failed",
        stage_progress=json.dumps({"enabled_stages": {**legacy_snapshot, "stories": True}}),
    )
    db_session.add(old)
    db_session.commit()

    svc = IngestionJobsService()
    retry = svc.create_job(db_session, novel.id, total_chapters=1)
    svc.set_enabled_stages(db_session, retry.id, _SNAPSHOT)
    db_session.commit()

    merged = IngestionJobsService.get_enabled_stages(retry)
    assert merged["stories"] is True
    assert merged["storylines"] is True
    assert merged["plots"] is False


@pytest.mark.integration
async def test_detail_exposes_counts_for_stage_gated_folders(client: AsyncClient, db_session):
    """The UI greys out a folder only when its stage is off AND it has no data."""
    from models.material_models import Chapter, Character, CharacterRelationship, Plot, Story

    user, token = await create_test_user(client, db_session, "stagesuser3")
    novel = create_test_novel(db_session, user.id, "Counted Novel")
    job = create_test_job(db_session, novel.id, "completed")
    IngestionJobsService().set_enabled_stages(db_session, job.id, _SNAPSHOT)
    chapter = Chapter(novel_id=novel.id, chapter_number=1, title="c1")
    char_a = Character(novel_id=novel.id, name="A")
    char_b = Character(novel_id=novel.id, name="B")
    db_session.add_all([chapter, char_a, char_b])
    db_session.commit()
    db_session.add_all([
        Plot(chapter_id=chapter.id, index=0, plot_type="SETUP", description="a"),
        Plot(chapter_id=chapter.id, index=1, plot_type="SETUP", description="b"),
        Story(novel_id=novel.id, title="s", synopsis="s"),
        CharacterRelationship(
            novel_id=novel.id, character_a_id=char_a.id, character_b_id=char_b.id, relationship_type="ally"
        ),
    ])
    db_session.commit()

    detail = await client.get(f"/api/v1/materials/{novel.id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    data = detail.json()
    assert (data["plots_count"], data["stories_count"], data["relationships_count"]) == (2, 1, 1)
