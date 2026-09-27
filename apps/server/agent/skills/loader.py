"""
Builtin skill loader.

内置技能以标准技能目录存放在 `builtin/<id>/SKILL.md`，是官方 PublicSkill 的唯一来源，
由 `services/builtin_skill_seed.py` 幂等写入数据库。运行时不再从磁盘读取技能。
"""

from dataclasses import dataclass
from pathlib import Path

from utils.logger import get_logger, log_with_context

from .package import SKILL_MD_FILENAME, ParsedSkill, SkillPackageError, parse_skill_md

logger = get_logger(__name__)

# Directory containing builtin skills
BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin"


@dataclass(frozen=True)
class BuiltinSkill:
    """A builtin skill loaded from `builtin/<id>/SKILL.md`."""

    id: str
    skill: ParsedSkill


def load_builtin_skills(base_dir: Path | None = None) -> list[BuiltinSkill]:
    """
    Load all builtin skills (sorted by directory name).

    解析失败的技能记日志后跳过，不影响其余技能。
    """
    skills_dir = base_dir or BUILTIN_SKILLS_DIR
    skills: list[BuiltinSkill] = []
    if not skills_dir.exists():
        return skills

    for skill_file in sorted(skills_dir.glob(f"*/{SKILL_MD_FILENAME}")):
        skill_id = skill_file.parent.name
        try:
            parsed = parse_skill_md(skill_file.read_text(encoding="utf-8"))
        except (OSError, SkillPackageError) as exc:
            log_with_context(
                logger, 40, "Failed to load builtin skill",
                file_path=str(skill_file),
                error=str(exc),
            )
            continue
        skills.append(BuiltinSkill(id=skill_id, skill=parsed))

    log_with_context(logger, 20, "Builtin skills loaded", total_count=len(skills))
    return skills
