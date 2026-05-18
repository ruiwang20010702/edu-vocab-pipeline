"""content_items 加 generated_with_prompt_id + generated_with_prompt_hash 双维识别字段.

G 方案：取代 24h 时间窗，按 prompt 版本判断"是否需要重新生产"。
nullable + 保留 NULL 老数据策略：首次重生会重做所有历史数据。

Revision ID: 022_add_gen_prompt_ref
Revises: 021_add_ai_task_queue
Create Date: 2026-05-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_add_gen_prompt_ref"
down_revision: Union[str, None] = "021_add_ai_task_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("generated_with_prompt_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_items",
        sa.Column("generated_with_prompt_hash", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_content_items_gen_prompt",
        "content_items",
        "prompts",
        ["generated_with_prompt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_content_items_gen_prompt",
        "content_items",
        ["generated_with_prompt_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_items_gen_prompt", table_name="content_items")
    op.drop_constraint("fk_content_items_gen_prompt", "content_items", type_="foreignkey")
    op.drop_column("content_items", "generated_with_prompt_hash")
    op.drop_column("content_items", "generated_with_prompt_id")
