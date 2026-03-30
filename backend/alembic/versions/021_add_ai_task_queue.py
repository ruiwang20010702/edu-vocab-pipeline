"""新增 ai_task_queue 表，持久化 Gateway 异步任务，支持提交/轮询解耦和重启恢复.

Revision ID: 021_add_ai_task_queue
Revises: 020_source_ids_to_varchar
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_add_ai_task_queue"
down_revision: Union[str, None] = "020_source_ids_to_varchar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_task_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        # 批次关联
        sa.Column("batch_key", sa.String(100), nullable=False),
        sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=True),
        # Gateway 交互
        sa.Column("gateway_task_no", sa.String(200), nullable=True),
        sa.Column("submit_body", sa.JSON(), nullable=True),
        # 状态
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(50), nullable=True),
        # 重试 & 轮询
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default="0"),
        # 时间戳
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # 关联元数据
        sa.Column("ai_model", sa.String(100), nullable=True),
        sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id", ondelete="SET NULL"), nullable=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("packages.id", ondelete="SET NULL"), nullable=True),
    )

    # 索引
    op.create_index("ix_aitq_status_created", "ai_task_queue", ["status", "created_at"])
    op.create_index("ix_aitq_batch_key", "ai_task_queue", ["batch_key"])
    op.create_index("ix_aitq_task_no", "ai_task_queue", ["gateway_task_no"], unique=True)
    op.create_index("ix_aitq_package_id", "ai_task_queue", ["package_id"])


def downgrade() -> None:
    op.drop_index("ix_aitq_package_id", table_name="ai_task_queue")
    op.drop_index("ix_aitq_task_no", table_name="ai_task_queue")
    op.drop_index("ix_aitq_batch_key", table_name="ai_task_queue")
    op.drop_index("ix_aitq_status_created", table_name="ai_task_queue")
    op.drop_table("ai_task_queue")
