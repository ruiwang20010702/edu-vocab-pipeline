"""新增 ai_usage_logs 表记录 AI 调用 token 用量和成本.

Revision ID: 015_add_ai_usage_logs
Revises: 014_remove_prompt_ai_api_key
Create Date: 2026-03-23
"""

import sqlalchemy as sa
from alembic import op

revision = "015_add_ai_usage_logs"
down_revision = "014_remove_prompt_ai_api_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=True),
        sa.Column("ai_model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float, nullable=True),
        sa.Column("elapsed_ms", sa.Integer, nullable=True),
        sa.Column("word_id", sa.Integer, sa.ForeignKey("words.id"), nullable=True),
        sa.Column(
            "content_item_id",
            sa.Integer,
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("gateway_task_no", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_ai_usage_logs_phase", "ai_usage_logs", ["phase"])
    op.create_index("ix_ai_usage_logs_dimension", "ai_usage_logs", ["dimension"])
    op.create_index("ix_ai_usage_logs_created_at", "ai_usage_logs", ["created_at"])
    op.create_index("ix_ai_usage_logs_content_item_id", "ai_usage_logs", ["content_item_id"])


def downgrade() -> None:
    op.drop_table("ai_usage_logs")
