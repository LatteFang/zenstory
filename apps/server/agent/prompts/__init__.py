"""Project writing configurations come exclusively from the primary database.

Shared runtime/role protocols remain code; project content is administered in DB.
"""

from typing import Any

from sqlmodel import Session, select

from core.error_codes import ErrorCode
from core.error_handler import APIException
from database import sync_engine

from .base import get_base_prompt
from .subagents import PLANNER_PROMPT, QUALITY_REVIEWER_PROMPT, WRITER_PROMPT
from .suggestions import get_suggestion_prompt

# In-memory cache for database configurations
_db_config_cache: dict[str, dict[str, Any]] | None = None


def _load_db_configs() -> dict[str, dict[str, Any]]:
    """
    Load all active system prompt configurations from database.

    Database errors intentionally propagate; missing rows never use source defaults.

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

    Missing or inactive configurations fail explicitly; no cross-type fallback.

    Args:
        project_type: Type of project (novel, short, screenplay)
        project_id: The project ID
        folder_ids: Dict mapping folder names to their IDs

    Returns:
        Complete system prompt string
    """
    db_configs = _load_db_configs()
    config = db_configs.get(project_type)

    if config is None:
        raise APIException(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            status_code=503,
            detail={
                "message": "Writing configuration is unavailable. An administrator must configure and reload this project type.",
                "project_type": project_type,
            },
        )

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
    "PLANNER_PROMPT",
    "WRITER_PROMPT",
    "QUALITY_REVIEWER_PROMPT",
]
