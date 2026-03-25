"""ReviewItem 添加部分唯一索引，防止同一 content_item 并发创建重复 pending 审核项.

Revision ID: 018_review_pending_uq
Revises: 017_pkg_time_usage_pkg
Create Date: 2026-03-25
"""

from alembic import op

revision = "018_review_pending_uq"
down_revision = "017_pkg_time_usage_pkg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 部分唯一索引：同一 content_item_id 只能有一条 pending 审核项
    op.execute(
        "CREATE UNIQUE INDEX uq_review_item_pending "
        "ON review_items (content_item_id) "
        "WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_review_item_pending")
