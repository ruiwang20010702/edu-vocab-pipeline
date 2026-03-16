"""新增 packages + package_meanings 表.

Revision ID: 003_add_package
Revises: 002_add_batch
Create Date: 2026-03-09
"""

import sqlalchemy as sa
from alembic import op

revision = "003_add_package"
down_revision = "002_add_batch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_words", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_words", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

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


def downgrade() -> None:
    op.drop_index("ix_package_meanings_meaning_id", "package_meanings")
    op.drop_index("ix_package_meanings_package_id", "package_meanings")
    op.drop_table("package_meanings")
    op.drop_table("packages")
