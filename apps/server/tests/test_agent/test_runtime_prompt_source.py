"""Runtime prompt DB authority boundary tests."""

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from agent import prompts
from models import SystemPromptConfig


def test_reload_eagerly_reads_primary_database_and_reports_metadata(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'prompts.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            SystemPromptConfig(
                project_type="novel",
                role_definition="Database role",
                capabilities="Database capabilities",
                version=6,
            )
        )
        session.commit()

    monkeypatch.setattr(prompts, "sync_engine", engine)
    prompts._db_config_cache = None

    result = prompts.reload_prompts()

    assert result == {"source": "primary_database", "count": 1, "version": 6}
    folder_ids = {
        "lore": "lore-id",
        "character": "character-id",
        "outline": "outline-id",
        "draft": "draft-id",
        "material": "material-id",
    }
    rendered = prompts.get_prompt_for_project_type("novel", "project-1", folder_ids)
    assert "Database role" in rendered


def test_database_unavailability_is_not_masked_by_file_defaults(monkeypatch):
    class BrokenSession:
        def __init__(self, _engine):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(prompts, "Session", BrokenSession)
    prompts._db_config_cache = None

    try:
        prompts.get_prompt_for_project_type("novel", "project-1", {})
    except RuntimeError as exc:
        assert str(exc) == "database unavailable"
    else:
        raise AssertionError("database failure was silently replaced with file defaults")


def test_runtime_prompt_store_uses_the_same_isolated_database_as_endpoint_fixtures(db_session):
    assert prompts.sync_engine is db_session.get_bind()
    db_session.add(SystemPromptConfig(project_type="novel", role_definition="Same test database", capabilities="Fixture capabilities", version=8))
    db_session.commit()
    result = prompts.reload_prompts()
    assert result == {"source": "primary_database", "count": 1, "version": 8}
