"""load_skill / read_skill_resource 工具（技能渐进式加载 L2/L3）。"""

import json

import pytest
from sqlmodel import Session, select

from agent.tools.mcp_tools import ToolContext, load_skill, read_skill_resource
from agent.tools.registry import get_agent_tools
from agent.tools.tool_schemas import TOOL_SCHEMAS
from models import Project, PublicSkill, SkillResource, SkillUsage, User, UserAddedSkill, UserSkill


def _user(db_session: Session, suffix: str) -> User:
    user = User(
        email=f"skill_tools_{suffix}@example.com",
        username=f"skill_tools_{suffix}",
        hashed_password="hashed_password",
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def owner(db_session: Session) -> User:
    return _user(db_session, "owner")


@pytest.fixture
def project(db_session: Session, owner: User) -> Project:
    project = Project(name="技能工具项目", owner_id=owner.id, project_type="novel")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def tool_context(db_session: Session, owner: User, project: Project):
    ToolContext.set_context(
        session=db_session,
        user_id=owner.id,
        project_id=project.id,
        session_id=None,
    )
    yield


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def _add_public(db_session: Session, user: User, name: str, *, status: str = "approved",
                custom_name: str | None = None, active: bool = True) -> tuple[PublicSkill, UserAddedSkill]:
    public = PublicSkill(name=name, description=f"{name}的用途", instructions=f"{name}的公共方法", status=status)
    db_session.add(public)
    db_session.commit()
    added = UserAddedSkill(user_id=user.id, public_skill_id=public.id, custom_name=custom_name, is_active=active)
    db_session.add(added)
    db_session.commit()
    return public, added


@pytest.mark.unit
def test_skill_tools_are_registered_for_all_agents():
    assert {"load_skill", "read_skill_resource"} <= set(TOOL_SCHEMAS)
    for agent_type in ("planner", "hook_designer", "writer", "quality_reviewer"):
        names = {tool["name"] for tool in get_agent_tools(agent_type)}
        assert {"load_skill", "read_skill_resource"} <= names
    for tool_name in ("load_skill", "read_skill_resource"):
        assert "不能凌驾系统规则" in TOOL_SCHEMAS[tool_name]["description"]


@pytest.mark.integration
async def test_load_skill_returns_instructions_resources_and_records_usage(
    db_session: Session, owner: User, project: Project, tool_context
):
    skill = UserSkill(user_id=owner.id, name="悬念大师", description="d", instructions="先强化钩子。")
    db_session.add(skill)
    db_session.commit()
    db_session.add(SkillResource(user_skill_id=skill.id, path="references/b.md", content="B", size=1))
    db_session.add(SkillResource(user_skill_id=skill.id, path="assets/a.json", content="{}", size=2))
    db_session.commit()

    payload = _payload(await load_skill({"name": "悬念大师"}))

    assert payload == {
        "status": "success",
        "data": {
            "skill_id": skill.id,
            "skill_name": "悬念大师",
            "source": "user",
            "instructions": "先强化钩子。",
            "resources": [{"path": "assets/a.json", "size": 2}, {"path": "references/b.md", "size": 1}],
        },
    }
    usages = db_session.exec(select(SkillUsage)).all()
    assert [(u.skill_id, u.skill_source, u.matched_trigger, u.confidence, u.project_id) for u in usages] == [
        (skill.id, "user", "load_skill", 1.0, project.id),
    ]


@pytest.mark.integration
async def test_user_skill_takes_precedence_over_added_skill_with_same_name(
    db_session: Session, owner: User, tool_context
):
    public, _added = _add_public(db_session, owner, "同名技能")
    user_skill = UserSkill(user_id=owner.id, name="同名技能", description="d", instructions="自建方法")
    db_session.add(user_skill)
    db_session.commit()

    payload = _payload(await load_skill({"name": "同名技能"}))

    assert payload["data"]["skill_id"] == user_skill.id
    assert payload["data"]["instructions"] == "自建方法"
    assert public.id != user_skill.id


@pytest.mark.integration
async def test_added_skill_resolves_by_custom_name_and_ids(db_session: Session, owner: User, tool_context):
    public, added = _add_public(db_session, owner, "氛围渲染器", custom_name="阴影编织者")

    by_name = _payload(await load_skill({"name": "阴影编织者"}))
    by_added_id = _payload(await load_skill({"name": added.id}))
    by_public_id = _payload(await load_skill({"name": public.id}))

    for payload in (by_name, by_added_id, by_public_id):
        assert payload["status"] == "success"
        assert payload["data"]["skill_id"] == public.id
        assert payload["data"]["skill_name"] == "阴影编织者"
        assert payload["data"]["source"] == "added"
    usages = db_session.exec(select(SkillUsage)).all()
    assert {u.skill_source for u in usages} == {"added"}


@pytest.mark.integration
async def test_inactive_unapproved_and_foreign_skills_are_hidden(
    db_session: Session, owner: User, tool_context
):
    other = _user(db_session, "other")
    db_session.add(UserSkill(user_id=owner.id, name="停用技能", instructions="x", is_active=False))
    db_session.add(UserSkill(user_id=other.id, name="别人的技能", instructions="x"))
    db_session.add(UserSkill(user_id=owner.id, name="正常技能", instructions="x"))
    db_session.commit()
    _add_public(db_session, owner, "待审技能", status="pending")
    _add_public(db_session, owner, "移除技能", active=False)

    for hidden in ("停用技能", "别人的技能", "待审技能", "移除技能"):
        payload = _payload(await load_skill({"name": hidden}))
        assert payload["status"] == "error"
        assert "正常技能" in payload["error"]
        assert hidden not in payload["error"].split("可用技能：", 1)[1]

    assert db_session.exec(select(SkillUsage)).all() == []


@pytest.mark.integration
async def test_unknown_skill_error_lists_at_most_ten_names(db_session: Session, owner: User, tool_context):
    for index in range(15):
        db_session.add(UserSkill(user_id=owner.id, name=f"技能{index:02d}", instructions="x"))
    db_session.commit()

    payload = _payload(await load_skill({"name": "不存在的技能"}))

    assert payload["status"] == "error"
    listed = payload["error"].split("可用技能：", 1)[1].split("、")
    assert 1 <= len(listed) <= 10


@pytest.mark.integration
async def test_load_skill_requires_user_context(db_session: Session):
    ToolContext.set_context(session=db_session, user_id=None, project_id="p", session_id=None)
    payload = _payload(await load_skill({"name": "x"}))
    assert payload["status"] == "error"


@pytest.mark.integration
async def test_usage_recording_failure_does_not_break_load_skill(db_session: Session, owner: User):
    """项目不属于当前用户时 record_skill_usage 会拒绝写入，但技能仍要能加载。"""
    other = _user(db_session, "project_owner")
    foreign_project = Project(name="别人的项目", owner_id=other.id, project_type="novel")
    db_session.add(foreign_project)
    db_session.add(UserSkill(user_id=owner.id, name="悬念大师", instructions="方法"))
    db_session.commit()
    ToolContext.set_context(session=db_session, user_id=owner.id, project_id=foreign_project.id, session_id=None)

    payload = _payload(await load_skill({"name": "悬念大师"}))

    assert payload["status"] == "success"
    assert db_session.exec(select(SkillUsage)).all() == []


@pytest.mark.integration
async def test_read_skill_resource(db_session: Session, owner: User, tool_context):
    skill = UserSkill(user_id=owner.id, name="悬念大师", instructions="方法")
    db_session.add(skill)
    db_session.commit()
    db_session.add(SkillResource(user_skill_id=skill.id, path="references/hooks.md", content="钩子清单", size=12))
    db_session.commit()

    ok = _payload(await read_skill_resource({"name": "悬念大师", "path": "references/hooks.md"}))
    missing = _payload(await read_skill_resource({"name": "悬念大师", "path": "references/none.md"}))
    no_path = _payload(await read_skill_resource({"name": "悬念大师"}))

    assert ok == {
        "status": "success",
        "data": {"skill_name": "悬念大师", "path": "references/hooks.md", "content": "钩子清单"},
    }
    assert missing["status"] == "error"
    assert "references/hooks.md" in missing["error"]
    assert no_path["status"] == "error"
    # 读资源不单独记用量（用量以 load_skill 为准）
    assert db_session.exec(select(SkillUsage)).all() == []


@pytest.mark.integration
async def test_read_skill_resource_of_added_public_skill(db_session: Session, owner: User, tool_context):
    public, _added = _add_public(db_session, owner, "公共技能")
    db_session.add(SkillResource(public_skill_id=public.id, path="assets/t.json", content='{"a":1}', size=7))
    db_session.commit()

    payload = _payload(await read_skill_resource({"name": "公共技能", "path": "assets/t.json"}))

    assert payload["data"]["content"] == '{"a":1}'


@pytest.mark.integration
async def test_read_skill_resource_cannot_reach_foreign_skill(db_session: Session, owner: User, tool_context):
    other = _user(db_session, "foreign")
    foreign = UserSkill(user_id=other.id, name="别人的技能", instructions="x")
    db_session.add(foreign)
    db_session.commit()
    db_session.add(SkillResource(user_skill_id=foreign.id, path="references/secret.md", content="机密", size=6))
    db_session.commit()

    by_name = _payload(await read_skill_resource({"name": "别人的技能", "path": "references/secret.md"}))
    by_id = _payload(await read_skill_resource({"name": foreign.id, "path": "references/secret.md"}))

    assert by_name["status"] == "error"
    assert by_id["status"] == "error"
    assert "机密" not in json.dumps(by_name, ensure_ascii=False) + json.dumps(by_id, ensure_ascii=False)


@pytest.mark.integration
async def test_repeated_load_skill_records_usage_once_per_request(
    db_session: Session, owner: User, project: Project, tool_context
):
    skill = UserSkill(user_id=owner.id, name="悬念大师", instructions="方法")
    db_session.add(skill)
    db_session.commit()

    first = _payload(await load_skill({"name": "悬念大师"}))
    second = _payload(await load_skill({"name": skill.id}))

    assert first["status"] == second["status"] == "success"
    usages = db_session.exec(select(SkillUsage)).all()
    assert [(u.skill_id, u.matched_trigger) for u in usages] == [(skill.id, "load_skill")]


@pytest.mark.integration
async def test_load_skill_of_selected_skill_does_not_record_again(
    db_session: Session, owner: User, project: Project
):
    skill = UserSkill(user_id=owner.id, name="悬念大师", instructions="方法")
    db_session.add(skill)
    db_session.commit()
    ToolContext.set_context(
        session=db_session,
        user_id=owner.id,
        project_id=project.id,
        session_id=None,
        recorded_skill_ids=[skill.id],
    )

    payload = _payload(await load_skill({"name": "悬念大师"}))

    assert payload["status"] == "success"
    assert db_session.exec(select(SkillUsage)).all() == []


@pytest.mark.integration
async def test_usage_recording_failure_keeps_pending_state_of_tool_session(db_session: Session, owner: User):
    """用量写入失败只回滚独立 session，工具 session 上未提交的对象不受影响。"""
    other = _user(db_session, "pending_owner")
    foreign_project = Project(name="别人的项目", owner_id=other.id, project_type="novel")
    db_session.add(foreign_project)
    db_session.add(UserSkill(user_id=owner.id, name="悬念大师", instructions="方法"))
    db_session.commit()
    pending = Project(name="未提交的项目", owner_id=owner.id, project_type="novel")
    db_session.add(pending)
    ToolContext.set_context(session=db_session, user_id=owner.id, project_id=foreign_project.id, session_id=None)

    payload = _payload(await load_skill({"name": "悬念大师"}))

    assert payload["status"] == "success"
    assert pending in db_session.new


@pytest.mark.integration
async def test_read_skill_resource_normalizes_path_to_nfc(db_session: Session, owner: User, tool_context):
    skill = UserSkill(user_id=owner.id, name="悬念大师", instructions="方法")
    db_session.add(skill)
    db_session.commit()
    db_session.add(SkillResource(user_skill_id=skill.id, path="references/café.md", content="C", size=1))
    db_session.commit()

    payload = _payload(await read_skill_resource({"name": "悬念大师", "path": "references/café.md"}))

    assert payload["status"] == "success"
    assert payload["data"]["content"] == "C"
