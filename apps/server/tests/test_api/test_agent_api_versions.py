"""
Agent API file updates must leave the same safety net as the web editor.

- PUT /api/v1/agent/files/{id} with changed content records a FileVersion attributed to
  the user (quota_source=user), so the change can be rolled back in version history.
- Title-only / no-op updates do not create versions.
- A full per-file version quota never blocks the content save.
- GET /api/v1/agent/projects/{id}/files pagination is deterministic (File.id tiebreaker).
"""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import Session, select

from models import File, FileVersion
from models.file_version import CHANGE_SOURCE_USER, CHANGE_TYPE_AI_EDIT
from models.subscription import SubscriptionPlan, UserSubscription
from services.features.file_version_service import FileVersionService
from tests.test_api.test_agent_api import (
    create_test_api_key,
    create_test_file,
    create_test_project,
    create_test_user,
)


def _versions(session: Session, file_id: str) -> list[FileVersion]:
    session.expire_all()
    return list(
        session.exec(
            select(FileVersion).where(FileVersion.file_id == file_id).order_by(FileVersion.version_number)
        ).all()
    )


def _bind_plan(session: Session, user_id: str, max_versions: int) -> None:
    plan = SubscriptionPlan(
        name=f"agent-api-version-quota-{user_id[:8]}",
        display_name="Agent API Version Quota",
        display_name_en="Agent API Version Quota",
        price_monthly_cents=999,
        price_yearly_cents=9999,
        features={"file_versions_per_file": max_versions},
        is_active=True,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    now = datetime.utcnow()
    session.add(
        UserSubscription(
            user_id=user_id,
            plan_id=plan.id,
            status="active",
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )
    )
    session.commit()


@pytest.mark.integration
async def test_agent_update_content_creates_user_version(client: AsyncClient, db_session: Session):
    user = create_test_user(db_session, "agent_version_user")
    project = create_test_project(db_session, user.id)
    file = create_test_file(db_session, project.id, "第一章", content="旧的正文。")
    _, plain_key = create_test_api_key(db_session, user.id, scopes=["read", "write"])

    response = await client.put(
        f"/api/v1/agent/files/{file.id}",
        headers={"X-Agent-API-Key": plain_key},
        json={"content": "新的正文。"},
    )

    assert response.status_code == 200
    assert response.json()["content"] == "新的正文。"
    versions = _versions(db_session, file.id)
    assert len(versions) == 1
    assert versions[0].change_source == CHANGE_SOURCE_USER
    assert versions[0].change_type == CHANGE_TYPE_AI_EDIT
    assert versions[0].change_summary == "Updated via Agent API"
    assert FileVersionService().get_content_at_version(db_session, file.id, versions[0].version_number) == "新的正文。"

    # A second edit adds another version; the first one stays restorable.
    response = await client.put(
        f"/api/v1/agent/files/{file.id}",
        headers={"X-Agent-API-Key": plain_key},
        json={"content": "再改一次。"},
    )
    assert response.status_code == 200
    versions = _versions(db_session, file.id)
    assert [v.version_number for v in versions] == [1, 2]
    assert FileVersionService().get_content_at_version(db_session, file.id, 1) == "新的正文。"


@pytest.mark.integration
async def test_agent_update_without_content_change_creates_no_version(client: AsyncClient, db_session: Session):
    user = create_test_user(db_session, "agent_version_noop_user")
    project = create_test_project(db_session, user.id)
    file = create_test_file(db_session, project.id, "第一章", content="同样的正文。")
    _, plain_key = create_test_api_key(db_session, user.id, scopes=["read", "write"])

    title_only = await client.put(
        f"/api/v1/agent/files/{file.id}",
        headers={"X-Agent-API-Key": plain_key},
        json={"title": "第一章 改名"},
    )
    same_content = await client.put(
        f"/api/v1/agent/files/{file.id}",
        headers={"X-Agent-API-Key": plain_key},
        json={"content": "同样的正文。"},
    )

    assert title_only.status_code == 200
    assert same_content.status_code == 200
    assert _versions(db_session, file.id) == []


@pytest.mark.integration
async def test_agent_update_saves_content_when_version_quota_is_full(client: AsyncClient, db_session: Session):
    user = create_test_user(db_session, "agent_version_quota_user")
    _bind_plan(db_session, user.id, max_versions=1)
    project = create_test_project(db_session, user.id)
    file = create_test_file(db_session, project.id, "第一章", content="v0")
    _, plain_key = create_test_api_key(db_session, user.id, scopes=["read", "write"])

    first = await client.put(
        f"/api/v1/agent/files/{file.id}", headers={"X-Agent-API-Key": plain_key}, json={"content": "v1"}
    )
    second = await client.put(
        f"/api/v1/agent/files/{file.id}", headers={"X-Agent-API-Key": plain_key}, json={"content": "v2"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["content"] == "v2"
    db_session.expire_all()
    assert db_session.get(File, file.id).content == "v2"
    assert len(_versions(db_session, file.id)) == 1


@pytest.mark.integration
async def test_agent_list_files_orders_ties_by_id(client: AsyncClient, db_session: Session):
    user = create_test_user(db_session, "agent_list_order_user")
    project = create_test_project(db_session, user.id)
    created_at = datetime(2026, 1, 1, 0, 0, 0)
    ids = []
    for i in range(6):
        f = File(
            project_id=project.id,
            title=f"Tie {i}",
            file_type="draft",
            content="",
            order=0,
            created_at=created_at,
            updated_at=created_at,
        )
        db_session.add(f)
        db_session.commit()
        ids.append(f.id)
    _, plain_key = create_test_api_key(db_session, user.id, scopes=["read"])

    seen: list[str] = []
    for offset in (0, 2, 4):
        response = await client.get(
            f"/api/v1/agent/projects/{project.id}/files",
            headers={"X-Agent-API-Key": plain_key},
            params={"limit": 2, "offset": offset, "fields": "id"},
        )
        assert response.status_code == 200
        seen.extend(f["id"] for f in response.json()["files"])

    assert seen == sorted(ids)
