"""Regression coverage for the backend inspiration-library feature flag."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from config.feature_flags import is_inspirations_enabled
from models import Inspiration, User
from services.core.auth_service import hash_password


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, False),
        ("true", True),
        (" TRUE ", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        (" FALSE ", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("unexpected", False),
        ("", False),
    ],
)
def test_inspirations_flag_parses_explicit_boolean_values(monkeypatch, raw_value, expected):
    if raw_value is None:
        monkeypatch.delenv("INSPIRATIONS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("INSPIRATIONS_ENABLED", raw_value)

    assert is_inspirations_enabled() is expected


@pytest.mark.integration
async def test_inspiration_routes_are_disabled_by_default(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.delenv("INSPIRATIONS_ENABLED", raising=False)

    response = await client.get("/api/v1/inspirations")

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/v1/inspirations", None),
        ("GET", "/api/v1/inspirations/featured", None),
        ("GET", "/api/v1/inspirations/my-submissions", None),
        ("GET", "/api/v1/inspirations/existing-inspiration", None),
        ("POST", "/api/v1/inspirations", {"project_id": "project-id"}),
        ("POST", "/api/v1/inspirations/existing-inspiration/copy", {}),
        ("GET", "/api/admin/inspirations", None),
        ("GET", "/api/admin/inspirations/existing-inspiration", None),
        ("POST", "/api/admin/inspirations", {"project_id": "project-id"}),
        ("PATCH", "/api/admin/inspirations/existing-inspiration", {"name": "changed"}),
        (
            "POST",
            "/api/admin/inspirations/existing-inspiration/review",
            {"approve": True},
        ),
        ("DELETE", "/api/admin/inspirations/existing-inspiration", None),
    ],
)
async def test_all_inspiration_endpoints_return_404_when_disabled(
    client: AsyncClient,
    monkeypatch,
    method: str,
    path: str,
    json_body: dict | None,
):
    monkeypatch.setenv("INSPIRATIONS_ENABLED", "false")

    response = await client.request(method, path, json=json_body)

    assert response.status_code == 404


@pytest.mark.integration
async def test_inspiration_routes_can_be_enabled_without_rebuilding_app(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setenv("INSPIRATIONS_ENABLED", "true")

    public_response = await client.get("/api/v1/inspirations")
    admin_response = await client.get("/api/admin/inspirations")

    assert public_response.status_code == 200
    assert admin_response.status_code == 401


@pytest.mark.integration
async def test_disabled_inspiration_feature_hides_points_opportunity_and_dashboard_counts(
    client: AsyncClient,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("INSPIRATIONS_ENABLED", "false")
    admin = User(
        username="feature_flag_admin",
        email="feature_flag_admin@example.com",
        hashed_password=hash_password("testpassword123"),
        email_verified=True,
        is_active=True,
        is_superuser=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    historical_inspiration = Inspiration(
        name="Hidden historical inspiration",
        project_type="novel",
        snapshot_data="{}",
        source="community",
        author_id=admin.id,
        status="pending",
    )
    db_session.add(historical_inspiration)
    db_session.commit()
    db_session.refresh(historical_inspiration)

    login_response = await client.post(
        "/api/auth/login",
        data={"username": admin.username, "password": "testpassword123"},
    )
    assert login_response.status_code == 200
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    opportunities_response = await client.get(
        "/api/v1/points/earn-opportunities",
        headers=headers,
    )
    dashboard_response = await client.get(
        "/api/admin/dashboard/stats",
        headers=headers,
    )
    copy_response = await client.post(
        f"/api/v1/inspirations/{historical_inspiration.id}/copy",
        json={},
        headers=headers,
    )
    review_response = await client.post(
        f"/api/admin/inspirations/{historical_inspiration.id}/review",
        json={"approve": True},
        headers=headers,
    )
    delete_response = await client.delete(
        f"/api/admin/inspirations/{historical_inspiration.id}",
        headers=headers,
    )

    assert opportunities_response.status_code == 200
    assert "inspiration_contribution" not in {
        item["type"] for item in opportunities_response.json()
    }
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["total_inspirations"] == 0
    assert dashboard_response.json()["pending_inspirations"] == 0
    assert copy_response.status_code == 404
    assert review_response.status_code == 404
    assert delete_response.status_code == 404

    db_session.expire_all()
    stored_inspiration = db_session.get(Inspiration, historical_inspiration.id)
    assert stored_inspiration is not None
    assert stored_inspiration.status == "pending"
    assert stored_inspiration.copy_count == 0
