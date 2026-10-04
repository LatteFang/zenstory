"""
AI Prompt templates for different project types.

This module provides modular prompt templates that can be customized
based on project type (novel, short story, screenplay).

The module loads prompt configurations from the application's primary database,
which is the same source used by the admin prompt API. Built-in Python
constants are a bootstrap fallback only when that database was read
successfully and has no active row for a requested project type.
"""

from typing import Any

from sqlmodel import Session, select

from database import sync_engine

from .base import get_base_prompt
from .novel import NOVEL_PROMPT_CONFIG
from .screenplay import SCREENPLAY_PROMPT_CONFIG
from .short_story import SHORT_STORY_PROMPT_CONFIG
from .subagents import PLANNER_PROMPT, QUALITY_REVIEWER_PROMPT, WRITER_PROMPT
from .suggestions import get_suggestion_prompt

# Map project types to their prompt configurations (fallback defaults)
PROMPT_CONFIGS: dict[str, dict[str, Any]] = {
    "novel": NOVEL_PROMPT_CONFIG,
    "short": SHORT_STORY_PROMPT_CONFIG,
    "screenplay": SCREENPLAY_PROMPT_CONFIG,
}

# In-memory cache for database configurations
_db_config_cache: dict[str, dict[str, Any]] | None = None


def _load_db_configs() -> dict[str, dict[str, Any]]:
    """
    Load all active system prompt configurations from database.

    Database errors intentionally propagate. File defaults are only a bootstrap
    fallback for project types without an active row after a successful read;
    they must not mask source unavailability.

    Returns:
        Dict mapping project_type to config dict
    """
    global _db_config_cache

    # Return cached configs if available
    if _db_config_cache is not None:
        return _db_config_cache

    db_configs, _version = _load_configs_from_engine(sync_engine)
    _db_config_cache = db_configs
    return db_configs


def _load_configs_from_engine(engine) -> tuple[dict[str, dict[str, Any]], int]:
    """
    Load prompt configurations from a specific database engine.

    Args:
        engine: SQLAlchemy engine to use
    Returns:
        Configs mapped by project type and the highest active config version.
    """
    configs = {}

    with Session(engine) as session:
        from models import SystemPromptConfig

        results = session.exec(
            select(SystemPromptConfig).where(SystemPromptConfig.is_active)
        ).all()

        for config in results:
            configs[config.project_type] = {
                "role_definition": config.role_definition,
                "capabilities": config.capabilities,
                "directory_structure": config.directory_structure or "",
                "content_structure": config.content_structure or "",
                "file_types": config.file_types or "",
                "writing_guidelines": config.writing_guidelines or "",
                "include_dialogue_guidelines": config.include_dialogue_guidelines,
            }

    max_version = max((config.version for config in results), default=0)
    return configs, max_version


def get_prompt_for_project_type(
    project_type: str,
    project_id: str,
    folder_ids: dict[str, str],
) -> str:
    """
    Get the complete system prompt for a project type.

    This function first tries to load the configuration from the database.
    If no database configuration exists, it falls back to the default
    file-based configuration.

    Args:
        project_type: Type of project (novel, short, screenplay)
        project_id: The project ID
        folder_ids: Dict mapping folder names to their IDs

    Returns:
        Complete system prompt string
    """
    # Try to get config from database first
    db_configs = _load_db_configs()
    config = db_configs.get(project_type)

    # Fall back to default file-based config if not in database
    if config is None:
        config = PROMPT_CONFIGS.get(project_type, PROMPT_CONFIGS["novel"])

    # Get base prompt with common sections
    base_prompt = get_base_prompt(project_id, folder_ids, config)

    return base_prompt


def reload_prompts() -> dict[str, int | str]:
    """
    Eagerly reload prompt configurations from the primary database.

    This function should be called when system prompt configurations are
    updated through the admin interface to ensure changes take effect immediately.
    """
    global _db_config_cache
    configs, version = _load_configs_from_engine(sync_engine)
    _db_config_cache = configs
    return {
        "source": "primary_database",
        "count": len(configs),
        "version": version,
    }


__all__ = [
    "get_prompt_for_project_type",
    "get_suggestion_prompt",
    "reload_prompts",
    "PROMPT_CONFIGS",
    "PLANNER_PROMPT",
    "WRITER_PROMPT",
    "QUALITY_REVIEWER_PROMPT",
]
