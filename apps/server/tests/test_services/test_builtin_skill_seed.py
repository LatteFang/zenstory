"""services.builtin_skill_seed：内置技能幂等写入公共技能库。"""

import json

import pytest
from sqlmodel import Session, select

from agent.skills.loader import BuiltinSkill, load_builtin_skills
from agent.skills.package import ParsedSkill
from models import PublicSkill
from services.builtin_skill_seed import seed_builtin_skills


@pytest.mark.unit
def test_seed_creates_all_builtin_skills_once(db_session: Session):
    builtins = load_builtin_skills()

    first = seed_builtin_skills(db_session)
    second = seed_builtin_skills(db_session)

    assert first == {"created": len(builtins), "updated": 0, "skipped": 0}
    assert second == {"created": 0, "updated": 0, "skipped": len(builtins)}

    public_skills = db_session.exec(select(PublicSkill)).all()
    assert len(public_skills) == len(builtins) == 13
    hook = next(skill for skill in public_skills if skill.name == "钩子设计")
    assert hook.source == "official"
    assert hook.status == "approved"
    assert hook.category == "plot"
    assert "钩子" in json.loads(hook.tags)
    assert hook.instructions.startswith("你现在进入钩子设计模式。")
    assert "【钩子设计】" in hook.instructions


@pytest.mark.unit
def test_seed_without_force_keeps_existing_rows(db_session: Session):
    builtin = BuiltinSkill(
        id="demo",
        skill=ParsedSkill(name="演示技能", description="新描述", instructions="新方法", triggers=["新"], category="style"),
    )
    existing = PublicSkill(name="演示技能", description="旧描述", instructions="旧方法", status="approved", add_count=7)
    db_session.add(existing)
    db_session.commit()

    result = seed_builtin_skills(db_session, builtin_skills=[builtin])

    db_session.refresh(existing)
    assert result == {"created": 0, "updated": 0, "skipped": 1}
    assert existing.instructions == "旧方法"


@pytest.mark.unit
def test_seed_with_force_overwrites_content_but_keeps_counters(db_session: Session):
    builtin = BuiltinSkill(
        id="demo",
        skill=ParsedSkill(
            name="演示技能", description="新描述", instructions="新方法", triggers=["新"], category="style",
            license="MIT",
        ),
    )
    existing = PublicSkill(
        name="演示技能", description="旧描述", instructions="旧方法",
        source="official", status="pending", add_count=7,
    )
    db_session.add(existing)
    db_session.commit()

    result = seed_builtin_skills(db_session, force=True, builtin_skills=[builtin])

    db_session.refresh(existing)
    assert result == {"created": 0, "updated": 1, "skipped": 0}
    assert (existing.description, existing.instructions, existing.category) == ("新描述", "新方法", "style")
    assert json.loads(existing.tags) == ["新"]
    assert json.loads(existing.skill_metadata) == {"license": "MIT"}
    assert (existing.source, existing.status, existing.add_count) == ("official", "approved", 7)
    assert len(db_session.exec(select(PublicSkill)).all()) == 1


@pytest.mark.unit
@pytest.mark.parametrize("force", [False, True])
def test_seed_ignores_same_name_community_skill(db_session: Session, force: bool):
    """社区用户分享的同名技能既不能让官方技能被跳过，也不能被 force 覆盖成官方技能。"""
    builtin = BuiltinSkill(
        id="demo",
        skill=ParsedSkill(name="演示技能", description="官方描述", instructions="官方方法", triggers=[]),
    )
    community = PublicSkill(
        name="演示技能", description="社区描述", instructions="社区方法",
        source="community", status="approved", add_count=3,
    )
    db_session.add(community)
    db_session.commit()

    result = seed_builtin_skills(db_session, force=force, builtin_skills=[builtin])

    db_session.refresh(community)
    assert result == {"created": 1, "updated": 0, "skipped": 0}
    assert (community.source, community.instructions, community.add_count) == ("community", "社区方法", 3)
    official = db_session.exec(
        select(PublicSkill).where(PublicSkill.name == "演示技能", PublicSkill.source == "official")
    ).one()
    assert official.instructions == "官方方法"
