import pytest
from httpx import AsyncClient
from sqlmodel import Session

from agent.suggest_service import FALLBACK_SUGGESTIONS_EN, FALLBACK_SUGGESTIONS_ZH
from models import File


@pytest.mark.integration
@pytest.mark.real_llm
async def test_suggest_real_llm_returns_quality_envelope(
    client: AsyncClient,
    db_session: Session,
    real_auth_context: dict,
    require_deepseek_key,
):
    context = real_auth_context
    user = context["user"]
    project = context["project"]

    db_session.add(
        File(
            title="Outline",
            content="Chapter 1: setup. Chapter 2: conflict.",
            file_type="outline",
            project_id=project.id,
            user_id=user.id,
        )
    )
    db_session.add(
        File(
            title="Draft 1",
            content="The protagonist enters a strange city and finds clues.",
            file_type="draft",
            project_id=project.id,
            user_id=user.id,
        )
    )
    db_session.commit()

    response = await client.post(
        "/api/v1/agent/suggest",
        json={
            "project_id": str(project.id),
            "count": 3,
            "recent_messages": [
                {"role": "user", "content": "I need help continuing the story."},
                {"role": "assistant", "content": "Focus on character conflict."},
            ],
        },
        headers=context["headers"],
    )
    assert response.status_code == 200

    data = response.json()
    suggestions = data.get("suggestions", [])
    assert len(suggestions) == 3
    assert all(isinstance(s, str) and len(s.strip()) >= 3 for s in suggestions)
    assert len(set(suggestions)) >= 2
    # 兜底文案同样满足上面的形状检查；必须确认是模型真的产出了建议
    # （deepseek-flash 的推理曾吃光 150 token 预算，导致静默回退）。
    fallback = set(FALLBACK_SUGGESTIONS_ZH) | set(FALLBACK_SUGGESTIONS_EN)
    assert not set(suggestions) <= fallback, suggestions
