"""
Builtin skill seed.

`agent/skills/builtin/<id>/SKILL.md` 是官方 PublicSkill 的唯一来源。本模块把它们幂等地
写入 public_skill 表（source="official"，status="approved"），按「名称 + 官方来源」去重。
"""

import json
from typing import TypedDict

from sqlmodel import Session, select

from agent.skills.loader import BuiltinSkill, load_builtin_skills
from config.datetime_utils import utcnow
from models import PublicSkill
from utils.logger import get_logger, log_with_context

logger = get_logger(__name__)

DEFAULT_BUILTIN_CATEGORY = "writing"


class SeedResult(TypedDict):
    created: int
    updated: int
    skipped: int


def _apply_builtin(public_skill: PublicSkill, builtin: BuiltinSkill) -> None:
    skill = builtin.skill
    public_skill.name = skill.name
    public_skill.description = skill.description
    public_skill.instructions = skill.instructions
    public_skill.category = skill.category or DEFAULT_BUILTIN_CATEGORY
    public_skill.tags = json.dumps(skill.triggers, ensure_ascii=False)
    public_skill.skill_metadata = json.dumps(skill.to_skill_metadata(), ensure_ascii=False)
    public_skill.source = "official"
    public_skill.status = "approved"


def seed_builtin_skills(
    session: Session,
    force: bool = False,
    builtin_skills: list[BuiltinSkill] | None = None,
) -> SeedResult:
    """
    Upsert builtin skills into PublicSkill, keyed by (name, source="official").

    Args:
        session: Database session (committed on return)
        force: True 时覆盖已存在的同名公共技能；False 时只创建缺失的
        builtin_skills: 测试注入用；默认从 builtin 目录加载

    Returns:
        created / updated / skipped counts
    """
    skills = builtin_skills if builtin_skills is not None else load_builtin_skills()
    result: SeedResult = {"created": 0, "updated": 0, "skipped": 0}

    for builtin in skills:
        # 必须同时匹配 source="official"：社区用户分享的同名技能不能被当成官方技能跳过或覆盖。
        existing = session.exec(
            select(PublicSkill).where(
                PublicSkill.name == builtin.skill.name,
                PublicSkill.source == "official",
            )
        ).first()

        if existing is None:
            public_skill = PublicSkill(name=builtin.skill.name, instructions="", add_count=0)
            _apply_builtin(public_skill, builtin)
            session.add(public_skill)
            result["created"] += 1
        elif force:
            _apply_builtin(existing, builtin)
            existing.updated_at = utcnow()
            session.add(existing)
            result["updated"] += 1
        else:
            result["skipped"] += 1

    session.commit()
    log_with_context(logger, 20, "Builtin skills seeded", force=force, **result)
    return result
