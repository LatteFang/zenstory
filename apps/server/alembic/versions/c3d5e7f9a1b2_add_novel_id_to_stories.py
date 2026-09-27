"""add novel_id to stories

剧情（stories）此前只能通过 story_line_id -> story_lines.novel_id 找到所属小说：
故事线生成失败或关闭时剧情对所有接口不可见；upsert 还按 title + synopsis 全局匹配，
可能把不同小说（甚至不同用户）的剧情合并到同一行。这里给 stories 增加 novel_id
（数据库层可空，兼容无法归属的历史行），并按以下顺序回填:

a. 经 story_line_id 取 story_lines.novel_id；
b. 仍为空的行：经 story_plot_links -> plots -> chapters.novel_id，仅当所有关联情节点
   指向同一本小说时回填；
c. 关联情节点跨越多本小说的行（历史跨小说合并的证据）：保留 a 的结果（若有），否则保持为空，
   只计数。

Revision ID: c3d5e7f9a1b2
Revises: b7e4c2a9d1f3
Create Date: 2026-09-27 18:00:00.000000

"""
import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b2'
down_revision: str | Sequence[str] | None = 'b7e4c2a9d1f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.migration.stories_novel_id")

_INDEX_NAME = 'ix_stories_novel_id'
_FK_NAME = 'fk_stories_novel_id_novels'

# 每个剧情的关联情节点所属小说：最小 novel_id 与去重后的小说数
_PLOT_NOVELS = """
    SELECT spl.story_id AS story_id,
           MIN(c.novel_id) AS novel_id,
           COUNT(DISTINCT c.novel_id) AS novel_count
    FROM story_plot_links spl
    JOIN plots p ON p.id = spl.plot_id
    JOIN chapters c ON c.id = p.chapter_id
    GROUP BY spl.story_id
"""


def _scalar(bind, sql: str) -> int:
    return int(bind.execute(sa.text(sql)).scalar() or 0)


def upgrade() -> None:
    # SQLite 不支持直接 ADD CONSTRAINT，batch_alter_table 在 SQLite 上重建表，在 PostgreSQL 上直接 ALTER。
    with op.batch_alter_table('stories') as batch_op:
        batch_op.add_column(sa.Column('novel_id', sa.Integer(), nullable=True))
        batch_op.create_index(_INDEX_NAME, ['novel_id'], unique=False)
        batch_op.create_foreign_key(_FK_NAME, 'novels', ['novel_id'], ['id'])

    bind = op.get_bind()
    total = _scalar(bind, "SELECT COUNT(*) FROM stories")

    # a. 经故事线回填
    bind.execute(sa.text(
        """
        UPDATE stories
        SET novel_id = (
            SELECT sl.novel_id FROM story_lines sl WHERE sl.id = stories.story_line_id
        )
        WHERE novel_id IS NULL AND story_line_id IS NOT NULL
        """
    ))
    via_storyline = _scalar(bind, "SELECT COUNT(*) FROM stories WHERE novel_id IS NOT NULL")

    # b. 经关联情节点回填（仅当所有情节点属于同一本小说）。
    # 直接按 story_plot_links.story_id 相关子查询，不做分组 CTE：后者在 SQLite 上
    # 会对每一行重跑整张聚合，近似二次复杂度。HAVING 不满足时子查询无行 -> 保持 NULL。
    bind.execute(sa.text(
        """
        UPDATE stories
        SET novel_id = (
            SELECT MIN(c.novel_id)
            FROM story_plot_links spl
            JOIN plots p ON p.id = spl.plot_id
            JOIN chapters c ON c.id = p.chapter_id
            WHERE spl.story_id = stories.id
            HAVING COUNT(DISTINCT c.novel_id) = 1
        )
        WHERE novel_id IS NULL
        """
    ))
    via_plots = _scalar(bind, "SELECT COUNT(*) FROM stories WHERE novel_id IS NOT NULL") - via_storyline

    # c. 关联情节点跨多本小说的行：不改动，只计数
    multi_novel = _scalar(
        bind, f"SELECT COUNT(*) FROM ({_PLOT_NOVELS}) pn WHERE pn.novel_count > 1"
    )
    multi_novel_unresolved = _scalar(
        bind,
        f"""
        SELECT COUNT(*) FROM stories
        WHERE novel_id IS NULL
          AND id IN (SELECT pn.story_id FROM ({_PLOT_NOVELS}) pn WHERE pn.novel_count > 1)
        """,
    )
    left_null = _scalar(bind, "SELECT COUNT(*) FROM stories WHERE novel_id IS NULL")

    logger.info(
        "stories.novel_id backfill: total=%d via_storyline=%d via_plots=%d "
        "multi_novel_plots=%d (kept_storyline_novel=%d, left_null=%d) left_null_total=%d",
        total,
        via_storyline,
        via_plots,
        multi_novel,
        multi_novel - multi_novel_unresolved,
        multi_novel_unresolved,
        left_null,
    )


def downgrade() -> None:
    with op.batch_alter_table('stories') as batch_op:
        batch_op.drop_index(_INDEX_NAME)
        batch_op.drop_column('novel_id')
