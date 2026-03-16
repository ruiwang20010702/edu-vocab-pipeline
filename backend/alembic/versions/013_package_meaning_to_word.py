"""PackageMeaning → PackageWord: meaning_id 改为 word_id.

无生产环境数据需要迁移，直接 drop + create。

Revision ID: 013_package_meaning_to_word
Revises: 012_add_ai_error_log_task_no
Create Date: 2026-03-16
"""

import sqlalchemy as sa
from alembic import op

revision = "013_package_meaning_to_word"
down_revision = "012_add_ai_error_log_task_no"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除旧表
    op.drop_index("ix_package_meanings_meaning_id", "package_meanings")
    op.drop_index("ix_package_meanings_package_id", "package_meanings")
    op.drop_table("package_meanings")

    # 创建新表
    op.create_table(
        "package_words",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "word_id", name="uq_package_words_pkg_word"),
    )
    op.create_index("ix_package_words_package_id", "package_words", ["package_id"])
    op.create_index("ix_package_words_word_id", "package_words", ["word_id"])


def downgrade() -> None:
    op.drop_index("ix_package_words_word_id", "package_words")
    op.drop_index("ix_package_words_package_id", "package_words")
    op.drop_table("package_words")

    # 恢复旧表
    op.create_table(
        "package_meanings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("meaning_id", sa.Integer(), sa.ForeignKey("meanings.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_package_meanings_package_id", "package_meanings", ["package_id"])
    op.create_index("ix_package_meanings_meaning_id", "package_meanings", ["meaning_id"])
