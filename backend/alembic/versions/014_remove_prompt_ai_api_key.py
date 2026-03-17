"""删除 prompts.ai_api_key 死字段（无代码读写，消除明文存储风险）.

Revision ID: 014_remove_prompt_ai_api_key
Revises: 013_package_meaning_to_word
Create Date: 2026-03-17
"""

import sqlalchemy as sa
from alembic import op

revision = "014_remove_prompt_ai_api_key"
down_revision = "013_package_meaning_to_word"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("prompts", "ai_api_key")


def downgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("ai_api_key", sa.String(200), nullable=True),
    )
