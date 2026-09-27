"""
Alembic 迁移 c3d5e7f9a1b2（stories.novel_id + 回填）在 SQLite 上的升降级。

与 test_skill_resource_migration 相同：先用当前模型建库、stamp 到本迁移、downgrade -1
去掉 novel_id，写入历史形态的数据，再 upgrade 验证回填 a/b/c，最后 downgrade 验证删列。
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
REVISION = "c3d5e7f9a1b2"
DOWN_REVISION = "b7e4c2a9d1f3"


def _alembic_executable() -> str:
    # 不能用 `python -m alembic`：cwd 下的 alembic/ 迁移目录会遮蔽已安装的 alembic 包。
    candidate = Path(sys.executable).parent / "alembic"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("alembic")
    assert found, "alembic CLI not found"
    return found


def _alembic(db_url: str, *args: str) -> str:
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
    return completed.stdout + completed.stderr


def _story_columns(engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("stories")}


def _version(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


_FIXTURE_SQL = [
    "INSERT INTO novels (id, user_id, title, created_at, updated_at) VALUES "
    "(1, 'u1', 'N1', '2026-01-01', '2026-01-01'), (2, 'u2', 'N2', '2026-01-01', '2026-01-01')",
    "INSERT INTO chapters (id, novel_id, chapter_number, title, created_at) VALUES "
    "(11, 1, 1, 'c1', '2026-01-01'), (21, 2, 1, 'c2', '2026-01-01')",
    "INSERT INTO plots (id, chapter_id, \"index\", plot_type, description, created_at) VALUES "
    "(111, 11, 0, 'SETUP', 'p', '2026-01-01'), (112, 11, 1, 'SETUP', 'p', '2026-01-01'), "
    "(211, 21, 0, 'SETUP', 'p', '2026-01-01')",
    "INSERT INTO story_lines (id, novel_id, title, created_at, updated_at) VALUES "
    "(5, 1, 'arc', '2026-01-01', '2026-01-01')",
    # s1: 经故事线归属 (a)；s2: 无故事线，情节点都在小说1 (b)；
    # s3: 无故事线，情节点跨小说 (c，保持为空)；s4: 有故事线且情节点跨小说 (c，保留 a 的结果)；
    # s6: 无故事线且无情节点（保持为空）；s7: 无故事线，唯一情节点在小说2 (b，归属另一本小说)
    "INSERT INTO stories (id, story_line_id, title, created_at, updated_at) VALUES "
    "(1, 5, 's1', '2026-01-01', '2026-01-01'), (2, NULL, 's2', '2026-01-01', '2026-01-01'), "
    "(3, NULL, 's3', '2026-01-01', '2026-01-01'), (4, 5, 's4', '2026-01-01', '2026-01-01'), "
    "(6, NULL, 's6', '2026-01-01', '2026-01-01'), (7, NULL, 's7', '2026-01-01', '2026-01-01')",
    "INSERT INTO story_plot_links (story_id, plot_id) VALUES "
    "(2, 111), (2, 112), (3, 111), (3, 211), (4, 112), (4, 211), (7, 211)",
]


@pytest.mark.integration
@pytest.mark.slow
def test_story_novel_id_migration_backfills_and_downgrades_on_sqlite(tmp_path: Path):
    db_url = f"sqlite:///{tmp_path / 'migration.db'}"
    engine = create_engine(db_url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    _alembic(db_url, "stamp", REVISION)
    _alembic(db_url, "downgrade", "-1")

    engine = create_engine(db_url)
    try:
        assert "novel_id" not in _story_columns(engine)
        assert _version(engine) == DOWN_REVISION
        with engine.begin() as conn:
            for statement in _FIXTURE_SQL:
                conn.execute(text(statement))
    finally:
        engine.dispose()

    output = _alembic(db_url, "upgrade", REVISION)
    assert (
        "total=6 via_storyline=2 via_plots=2 multi_novel_plots=2 "
        "(kept_storyline_novel=1, left_null=1) left_null_total=2"
    ) in output

    engine = create_engine(db_url)
    try:
        assert "novel_id" in _story_columns(engine)
        inspector = inspect(engine)
        assert "ix_stories_novel_id" in {index["name"] for index in inspector.get_indexes("stories")}
        assert any(
            fk["referred_table"] == "novels" and fk["constrained_columns"] == ["novel_id"]
            for fk in inspector.get_foreign_keys("stories")
        )
        with engine.connect() as conn:
            rows = dict(conn.execute(text("SELECT id, novel_id FROM stories ORDER BY id")).all())
        assert rows == {1: 1, 2: 1, 3: None, 4: 1, 6: None, 7: 2}
        assert _version(engine) == REVISION
    finally:
        engine.dispose()

    _alembic(db_url, "downgrade", "-1")

    engine = create_engine(db_url)
    try:
        assert "novel_id" not in _story_columns(engine)
        assert "ix_stories_novel_id" not in {index["name"] for index in inspect(engine).get_indexes("stories")}
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM stories")).scalar_one() == 6
            assert conn.execute(text("SELECT COUNT(*) FROM story_plot_links")).scalar_one() == 7
        assert _version(engine) == DOWN_REVISION
    finally:
        engine.dispose()
