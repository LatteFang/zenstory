"""
Skills system for the AI writing assistant.

Skills follow the standard Agent Skills format (SKILL.md + references/ + assets/).
They are disclosed progressively: the system prompt lists name + description (L1),
the `load_skill` tool returns instructions (L2), and `read_skill_resource` returns
one resource file (L3). Skill code is never executed.
"""

from .active_skills import ActiveSkill, load_active_skills, resolve_selected_skills
from .context_injector import SkillContextInjector, get_skill_context_injector
from .package import ParsedSkill, SkillPackageError, build_skill_zip, parse_skill_md, read_skill_zip

__all__ = [
    "ActiveSkill",
    "ParsedSkill",
    "SkillContextInjector",
    "SkillPackageError",
    "build_skill_zip",
    "get_skill_context_injector",
    "load_active_skills",
    "parse_skill_md",
    "read_skill_zip",
    "resolve_selected_skills",
]
