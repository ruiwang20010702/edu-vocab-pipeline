"""新增 ai_error_logs 表记录 AI 调用失败.

Revision ID: 007_add_ai_error_logs
Revises: eb1d3d8b6d1c
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "007_add_ai_error_logs"
down_revision = "eb1d3d8b6d1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_error_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_item_id", sa.Integer(), nullable=True),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=True),
        sa.Column("error_type", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("ai_model", sa.String(100), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"]),
    )
    op.create_index("ix_ai_error_logs_content_item_id", "ai_error_logs", ["content_item_id"])
    op.create_index("ix_ai_error_logs_phase", "ai_error_logs", ["phase"])
    op.create_index("ix_ai_error_logs_word_id", "ai_error_logs", ["word_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_error_logs_word_id", table_name="ai_error_logs")
    op.drop_index("ix_ai_error_logs_phase", table_name="ai_error_logs")
    op.drop_index("ix_ai_error_logs_content_item_id", table_name="ai_error_logs")
    op.drop_table("ai_error_logs")
