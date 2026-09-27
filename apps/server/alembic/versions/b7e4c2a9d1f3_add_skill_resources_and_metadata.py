"""add skill resources and standard skill metadata

新增 skill_resource 表（技能包的 references/、assets/ 文本资源），
user_skill / public_skill 增加 skill_metadata（标准 frontmatter 其余字段的 JSON），
description 放宽到 1024（与 Agent Skills 标准一致）。

Revision ID: b7e4c2a9d1f3
Revises: a1f2c3d4e5b6
Create Date: 2026-09-27 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e4c2a9d1f3'
down_revision: str | Sequence[str] | None = 'a1f2c3d4e5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SKILL_TABLES = ('user_skill', 'public_skill')


def upgrade() -> None:
    # SQLite 不支持 ALTER COLUMN，batch_alter_table 在 SQLite 上重建表，在 PostgreSQL 上直接 ALTER。
    for table_name in _SKILL_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column('skill_metadata', sa.Text(), nullable=False, server_default='{}'),
            )
            batch_op.alter_column(
                'description',
                existing_type=sa.String(length=500),
                type_=sa.String(length=1024),
                existing_nullable=True,
            )

    op.create_table(
        'skill_resource',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_skill_id', sa.String(), nullable=True),
        sa.Column('public_skill_id', sa.String(), nullable=True),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            '(user_skill_id IS NULL) <> (public_skill_id IS NULL)',
            name='ck_skill_resource_single_owner',
        ),
        sa.ForeignKeyConstraint(['user_skill_id'], ['user_skill.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['public_skill_id'], ['public_skill.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_skill_id', 'path', name='uq_skill_resource_user_skill_path'),
        sa.UniqueConstraint('public_skill_id', 'path', name='uq_skill_resource_public_skill_path'),
    )
    op.create_index('ix_skill_resource_user_skill_id', 'skill_resource', ['user_skill_id'])
    op.create_index('ix_skill_resource_public_skill_id', 'skill_resource', ['public_skill_id'])


def downgrade() -> None:
    op.drop_index('ix_skill_resource_public_skill_id', table_name='skill_resource')
    op.drop_index('ix_skill_resource_user_skill_id', table_name='skill_resource')
    op.drop_table('skill_resource')

    for table_name in _SKILL_TABLES:
        # 收窄前先截断超长描述，否则 PostgreSQL 的类型收窄会失败。
        op.execute(
            sa.text(
                f"UPDATE {table_name} SET description = substr(description, 1, 500) "
                "WHERE length(description) > 500"
            )
        )
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                'description',
                existing_type=sa.String(length=1024),
                type_=sa.String(length=500),
                existing_nullable=True,
            )
            batch_op.drop_column('skill_metadata')
