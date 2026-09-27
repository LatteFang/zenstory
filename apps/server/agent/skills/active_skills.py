"""
当前用户「启用中」技能的统一视图。

技能目录（L1）、`load_skill` / `read_skill_resource` 工具（L2/L3）、显式选择的
`selected_skill_ids` 都从这里取数，保证三处看到的是同一批技能、同一套优先级：
用户自建技能 > 已添加的公共技能（仅 approved）。
"""

import difflib
from dataclasses import dataclass

from sqlmodel import Session, select

from models import PublicSkill, SkillResource, UserAddedSkill, UserSkill

# 显式选择的技能数上限（与前端 SkillTriggerContext 一致）
MAX_SELECTED_SKILLS = 3


@dataclass(frozen=True)
class ActiveSkill:
    """A skill the current user can use in this turn."""

    # 规范 ID：自建技能为 UserSkill.id，已添加技能为 PublicSkill.id（用量统计沿用此口径）
    id: str
    name: str
    description: str
    instructions: str
    source: str  # "user" | "added"
    # 已添加技能在 GET /skills 列表里的 ID（UserAddedSkill.id）
    added_id: str | None = None

    @property
    def user_skill_id(self) -> str | None:
        return self.id if self.source == "user" else None

    @property
    def public_skill_id(self) -> str | None:
        return self.id if self.source == "added" else None


def load_active_skills(session: Session, user_id: str) -> list[ActiveSkill]:
    """
    Load all active skills available to a user, in deterministic order.

    order_by 不可省：没有它时返回顺序由数据库堆序决定，PostgreSQL 上任何一次 UPDATE
    都会把元组重写到堆尾，目录顺序会在用户编辑技能后无声漂移，破坏 prompt 缓存。
    """
    skills: list[ActiveSkill] = []

    user_stmt = select(UserSkill).where(
        UserSkill.user_id == user_id,
        UserSkill.is_active,
    ).order_by(UserSkill.created_at, UserSkill.id)
    for skill in session.exec(user_stmt).all():
        skills.append(ActiveSkill(
            id=skill.id,
            name=skill.name,
            description=skill.description or "",
            instructions=skill.instructions or "",
            source="user",
        ))

    added_stmt = select(UserAddedSkill, PublicSkill).join(
        PublicSkill, UserAddedSkill.public_skill_id == PublicSkill.id
    ).where(
        UserAddedSkill.user_id == user_id,
        UserAddedSkill.is_active,
        PublicSkill.status == "approved",
    ).order_by(UserAddedSkill.added_at, UserAddedSkill.id)
    for added, public in session.exec(added_stmt).all():
        skills.append(ActiveSkill(
            id=public.id,
            name=added.custom_name or public.name,
            description=public.description or "",
            instructions=public.instructions or "",
            source="added",
            added_id=added.id,
        ))

    return skills


def find_active_skill(skills: list[ActiveSkill], name_or_id: str) -> ActiveSkill | None:
    """
    按显示名或 ID 查找技能。

    先精确匹配名称，再忽略大小写/首尾空白匹配名称，最后匹配 ID；
    列表本身已按「自建 > 已添加」排序，同名时自建技能胜出。
    """
    query = (name_or_id or "").strip()
    if not query:
        return None

    for skill in skills:
        if skill.name == query:
            return skill

    folded = query.casefold()
    for skill in skills:
        if skill.name.strip().casefold() == folded:
            return skill

    for skill in skills:
        if query in (skill.id, skill.added_id):
            return skill

    return None


def suggest_skill_names(skills: list[ActiveSkill], name: str, limit: int = 10) -> list[str]:
    """找不到技能时给模型的候选名：优先相近名称，没有相近的就列出前若干个。"""
    names: list[str] = []
    for skill in skills:
        if skill.name not in names:
            names.append(skill.name)
    close = difflib.get_close_matches((name or "").strip(), names, n=limit, cutoff=0.3)
    return close or names[:limit]


def resolve_selected_skills(
    session: Session,
    user_id: str,
    skill_ids: list[str] | None,
) -> list[ActiveSkill]:
    """
    解析前端显式选择的技能 ID（UserSkill.id / UserAddedSkill.id / 已添加的 PublicSkill.id）。

    只接受属于当前用户且启用中的技能；其余 ID 静默忽略。最多 MAX_SELECTED_SKILLS 个，按请求顺序去重。
    """
    wanted = [str(item).strip() for item in (skill_ids or []) if str(item or "").strip()]
    if not wanted:
        return []

    active = load_active_skills(session, user_id)
    selected: list[ActiveSkill] = []
    seen: set[str] = set()
    for skill_id in wanted:
        match = next(
            (skill for skill in active if skill_id in (skill.id, skill.added_id)),
            None,
        )
        if match is None or match.id in seen:
            continue
        seen.add(match.id)
        selected.append(match)
        if len(selected) >= MAX_SELECTED_SKILLS:
            break
    return selected


def _resource_owner_filter(user_skill_id: str | None, public_skill_id: str | None):
    if user_skill_id:
        return SkillResource.user_skill_id == user_skill_id
    if public_skill_id:
        return SkillResource.public_skill_id == public_skill_id
    raise ValueError("Either user_skill_id or public_skill_id is required")


def list_skill_resources(
    session: Session,
    *,
    user_skill_id: str | None = None,
    public_skill_id: str | None = None,
) -> list[SkillResource]:
    """List resources of one skill, ordered by path."""
    stmt = select(SkillResource).where(
        _resource_owner_filter(user_skill_id, public_skill_id)
    ).order_by(SkillResource.path)
    return list(session.exec(stmt).all())


def get_skill_resource(
    session: Session,
    path: str,
    *,
    user_skill_id: str | None = None,
    public_skill_id: str | None = None,
) -> SkillResource | None:
    """Get one resource of a skill by path."""
    stmt = select(SkillResource).where(
        _resource_owner_filter(user_skill_id, public_skill_id),
        SkillResource.path == path,
    )
    return session.exec(stmt).first()


def list_active_skill_resources(session: Session, skill: ActiveSkill) -> list[SkillResource]:
    return list_skill_resources(
        session,
        user_skill_id=skill.user_skill_id,
        public_skill_id=skill.public_skill_id,
    )
