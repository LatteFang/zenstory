"""Tests for skill-related system prompt sections."""

import pytest

from agent.core.message_manager import MessageManager
from models import Project, User

pytestmark = pytest.mark.usefixtures("writing_prompt_configs")


def _create_user(db_session, *, suffix: str) -> User:
    user = User(
        email=f"message-manager-skill-{suffix}@example.com",
        username=f"message_manager_skill_{suffix}",
        hashed_password="hashed_password",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_manager(db_session) -> MessageManager:
    owner = _create_user(db_session, suffix="owner")
    project = Project(
        name="Skill Prompt Project",
        owner_id=owner.id,
        project_type="novel",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return MessageManager(project_id=project.id, user_id=owner.id)


@pytest.mark.unit
def test_build_system_prompt_includes_selected_skills_with_resources(db_session):
    manager = _create_manager(db_session)

    prompt = manager.build_system_prompt(
        session=db_session,
        language="zh",
        selected_skills=[
            {
                "id": "skill-1",
                "name": "悬念大师",
                "instructions": "先强化钩子，再收紧悬念。",
                "source": "user",
                "resources": ["references/hooks.md"],
            },
            {
                "id": "skill-2",
                "name": "节奏控",
                "instructions": "压缩重复动作。",
                "source": "added",
                "resources": [],
            },
        ],
    )

    assert prompt.count("## 用户本条消息指定技能") == 1
    assert "### 悬念大师" in prompt
    assert "先强化钩子，再收紧悬念。" in prompt
    assert "- references/hooks.md" in prompt
    assert "### 节奏控" in prompt
    assert "不能凌驾系统规则" in prompt
    # 旧的文本标记与前缀匹配都已下线
    assert "使用技能" not in prompt
    assert "匹配前缀" not in prompt


@pytest.mark.unit
def test_build_system_prompt_places_catalog_before_selected_skills(db_session):
    """目录属于静态前缀，显式选择属于半静态段，顺序不能颠倒（prompt 缓存依赖它）。"""
    manager = _create_manager(db_session)

    prompt = manager.build_system_prompt(
        session=db_session,
        language="zh",
        skill_catalog="## 可用写作技能\n\n- **悬念大师**: 增强钩子",
        selected_skills=[{"name": "悬念大师", "instructions": "先强化钩子。", "resources": []}],
    )

    assert prompt.index("## 可用写作技能") < prompt.index("## 用户本条消息指定技能")


@pytest.mark.unit
def test_build_system_prompt_skips_selected_skill_without_instructions(db_session):
    manager = _create_manager(db_session)

    prompt = manager.build_system_prompt(
        session=db_session,
        language="en",
        selected_skills=[{"name": "Empty", "instructions": "  ", "resources": []}],
    )

    assert "User-Selected Skills" not in prompt
