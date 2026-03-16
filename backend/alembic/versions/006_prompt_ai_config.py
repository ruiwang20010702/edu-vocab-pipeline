"""Prompt 表增加 AI 厂商配置字段.

Revision ID: 006_prompt_ai_config
Revises: 005_fix_schema
Create Date: 2026-03-09
"""

import sqlalchemy as sa
from alembic import op

revision = "006_prompt_ai_config"
down_revision = "005_fix_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("ai_api_key", sa.String(200), nullable=True))
    op.add_column("prompts", sa.Column("ai_api_base_url", sa.String(500), nullable=True))
    # 更新默认 model 值
    op.alter_column("prompts", "model", server_default="gemini-3-flash-preview", existing_type=sa.String(50))


def downgrade() -> None:
    op.alter_column("prompts", "model", server_default="gpt-4o-mini", existing_type=sa.String(50))
    op.drop_column("prompts", "ai_api_base_url")
    op.drop_column("prompts", "ai_api_key")
