"""review_items 加复合索引 (content_item_id, status, resolved_at DESC) 加速导出审核人聚合.

P-M1 export profile 发现 _collect_reviewers_for_meaning 用大 IN 查询
WHERE content_item_id IN (...) AND status='resolved' ORDER BY resolved_at DESC，
但原有索引只有单列 (content_item_id) + (status, assigned_to_id) + partial
(content_item_id) UNIQUE WHERE status='pending'，恰好不覆盖该查询，27 万规模会
退化为 Bitmap Heap Scan + Sort。新建复合索引让该查询 cover Index Scan + 已排序。

Revision ID: 023_review_items_idx
Revises: 022_add_gen_prompt_ref
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "023_review_items_idx"
down_revision: Union[str, None] = "022_add_gen_prompt_ref"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_review_items_ci_status_resolved",
        "review_items",
        ["content_item_id", "status", "resolved_at"],
        unique=False,
        postgresql_ops={"resolved_at": "DESC NULLS LAST"},
    )


def downgrade() -> None:
    op.drop_index("ix_review_items_ci_status_resolved", table_name="review_items")
