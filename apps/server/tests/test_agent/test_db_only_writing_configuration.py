"""DB-only prompt authority: missing/inactive types never use source defaults."""

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from agent import prompts
from core.error_codes import ErrorCode
from core.error_handler import APIException
from models import SystemPromptConfig

FOLDER_IDS = {
    "lore": "lore-id", "character": "character-id", "outline": "outline-id",
    "draft": "draft-id", "script": "script-id", "material": "material-id",
}


@pytest.fixture
def isolated_prompt_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'writing-config.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(prompts, "sync_engine", engine)
    monkeypatch.setattr(prompts, "_db_config_cache", None)
    yield engine
    engine.dispose()


def assert_configuration_unavailable(project_type):
    with pytest.raises(APIException) as caught:
        prompts.get_prompt_for_project_type(project_type, "project-id", FOLDER_IDS)
    assert caught.value.status_code == 503
    assert caught.value.error_code == ErrorCode.SERVICE_UNAVAILABLE
    assert project_type in str(caught.value.detail)


@pytest.mark.unit
@pytest.mark.parametrize("project_type", ["novel", "short", "screenplay", "unknown"])
def test_missing_project_type_has_no_source_or_other_type_fallback(isolated_prompt_engine, project_type):
    assert_configuration_unavailable(project_type)


@pytest.mark.unit
def test_inactive_prompt_cannot_be_replaced_with_source_defaults(isolated_prompt_engine):
    with Session(isolated_prompt_engine) as session:
        session.add(SystemPromptConfig(
            project_type="novel", role_definition="Inactive role", capabilities="Inactive capabilities",
            is_active=False,
        ))
        session.commit()
    assert_configuration_unavailable("novel")


@pytest.mark.unit
def test_another_active_project_type_is_not_a_fallback(isolated_prompt_engine):
    with Session(isolated_prompt_engine) as session:
        session.add(SystemPromptConfig(
            project_type="novel", role_definition="Only novel role", capabilities="Only novel capabilities",
        ))
        session.commit()
    assert_configuration_unavailable("short")
