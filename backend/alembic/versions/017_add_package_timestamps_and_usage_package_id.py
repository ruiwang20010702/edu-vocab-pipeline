"""Package 新增 started_at/completed_at + AiUsageLog 新增 package_id.

Revision ID: 017_pkg_time_usage_pkg
Revises: 016_importing_status
Create Date: 2026-03-24
"""

import sqlalchemy as sa
from alembic import op

revision = "017_pkg_time_usage_pkg"
down_revision = "016_importing_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("packages", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("packages", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("ai_usage_logs", sa.Column("package_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ai_usage_logs_package_id",
        "ai_usage_logs",
        "packages",
        ["package_id"],
        ["id"],
    )
    op.create_index("ix_ai_usage_logs_package_id", "ai_usage_logs", ["package_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_package_id", table_name="ai_usage_logs")
    op.drop_constraint("fk_ai_usage_logs_package_id", "ai_usage_logs", type_="foreignkey")
    op.drop_column("ai_usage_logs", "package_id")

    op.drop_column("packages", "completed_at")
    op.drop_column("packages", "started_at")
