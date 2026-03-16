"""新增 AiErrorLog.gateway_task_no 字段，记录 Gateway 异步任务编号。

Revision ID: 012_add_ai_error_log_task_no
Revises: 011_add_ai_error_log_details
Create Date: 2026-03-16
"""

import sqlalchemy as sa
from alembic import op

revision = "012_add_ai_error_log_task_no"
down_revision = "011_add_ai_error_log_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_error_logs", sa.Column("gateway_task_no", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_error_logs", "gateway_task_no")
