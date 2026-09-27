"""
Alembic 迁移 b7e4c2a9d1f3（skill_resource + skill_metadata + description 1024）在 SQLite 上的升降级。

历史迁移无法在空库上从头跑通（初始表由 create_all 建立），所以这里先用当前模型建库、
stamp 到本迁移，再验证 downgrade -1 → upgrade 本迁移 的往返（head 之后的迁移不参与）。alembic 在子进程里跑：
env.py 会 fileConfig 重置日志，并读取 DATABASE_URL 环境变量。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlmodel import SQLModel

import models  # noqa: F401  (register all tables)

SERVER_DIR = Path(__file__).resolve().parents[2]
REVISION = "b7e4c2a9d1f3"
DOWN_REVISION = "a1f2c3d4e5b6"


def _alembic_executable() -> str:
    # 不能用 `python -m alembic`：cwd 下的 alembic/ 迁移目录会遮蔽已安装的 alembic 包。
    candidate = Path(sys.executable).parent / "alembic"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("alembic")
    assert found, "alembic CLI not found"
    return found


def _alembic(db_url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": db_url}
    completed = subprocess.run(
        [_alembic_executable(), *args],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _columns(engine, table: str) -> dict[str, object]:
    return {column["name"]: column for column in inspect(engine).get_columns(table)}


@pytest.mark.integration
@pytest.mark.slow
def test_skill_resource_migration_downgrade_and_upgrade_on_sqlite(tmp_path: Path):
    db_url = f"sqlite:///{tmp_path / 'migration.db'}"
    engine = create_engine(db_url)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO user (id, email, username, hashed_password, is_active, email_verified, "
            "is_superuser, created_at, updated_at) VALUES "
            "('u1', 'm@example.com', 'm', 'x', 1, 1, 0, '2026-01-01', '2026-01-01')"
        ))
        conn.execute(text(
            "INSERT INTO user_skill (id, user_id, name, description, triggers, instructions, "
            "skill_metadata, is_active, is_shared, created_at, updated_at) VALUES "
            "('s1', 'u1', '技能', :description, '[]', '方法', '{\"license\": \"MIT\"}', 1, 0, "
            "'2026-01-01', '2026-01-01')"
        ), {"description": "长" * 800})
    engine.dispose()

    _alembic(db_url, "stamp", REVISION)
    _alembic(db_url, "downgrade", "-1")

    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        assert "skill_resource" not in inspector.get_table_names()
        for table in ("user_skill", "public_skill"):
            columns = _columns(engine, table)
            assert "skill_metadata" not in columns
            assert columns["description"]["type"].length == 500
        with engine.connect() as conn:
            row = conn.execute(text("SELECT name, description FROM user_skill WHERE id = 's1'")).one()
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        # 降级前截断超长描述，数据行本身保留
        assert row.name == "技能"
        assert len(row.description) == 500
        assert version == DOWN_REVISION
    finally:
        engine.dispose()

    _alembic(db_url, "upgrade", REVISION)

    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        assert "skill_resource" in inspector.get_table_names()
        resource_columns = set(_columns(engine, "skill_resource"))
        assert resource_columns == {
            "id", "user_skill_id", "public_skill_id", "path", "content", "size", "created_at", "updated_at",
        }
        unique_names = {item["name"] for item in inspector.get_unique_constraints("skill_resource")}
        assert unique_names == {"uq_skill_resource_user_skill_path", "uq_skill_resource_public_skill_path"}
        for table in ("user_skill", "public_skill"):
            columns = _columns(engine, table)
            assert "skill_metadata" in columns
            assert columns["description"]["type"].length == 1024
        with engine.begin() as conn:
            row = conn.execute(text("SELECT skill_metadata FROM user_skill WHERE id = 's1'")).one()
            assert row.skill_metadata == "{}"
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == REVISION
            # 恰好一个 owner 的检查约束生效
            with pytest.raises(Exception, match="CHECK"):
                conn.execute(text(
                    "INSERT INTO skill_resource (id, user_skill_id, public_skill_id, path, content, size, "
                    "created_at, updated_at) VALUES ('r1', NULL, NULL, 'references/a.md', 'a', 1, "
                    "'2026-01-01', '2026-01-01')"
                ))
    finally:
        engine.dispose()
