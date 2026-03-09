"""新增 prompts 表.

Revision ID: 004_add_prompts
Revises: 003_add_package
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa

revision = "004_add_prompts"
down_revision = "003_add_package"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("model", sa.String(50), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompts_category_dimension", "prompts", ["category", "dimension"])


def downgrade() -> None:
    op.drop_index("ix_prompts_category_dimension", "prompts")
    op.drop_table("prompts")
