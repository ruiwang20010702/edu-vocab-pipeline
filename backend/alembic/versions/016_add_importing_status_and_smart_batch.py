"""Package status 新增 importing 状态 + 生产优化配置.

Revision ID: 016_add_importing_status_and_smart_batch
Revises: 015_add_ai_usage_logs
Create Date: 2026-03-24
"""

from alembic import op

revision = "016_importing_status"
down_revision = "015_add_ai_usage_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 更新 Package status 的 check constraint，新增 'importing' 状态
    op.drop_constraint("ck_packages_status", "packages", type_="check")
    op.create_check_constraint(
        "ck_packages_status",
        "packages",
        "status IN ('importing', 'pending', 'processing', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_packages_status", "packages", type_="check")
    op.create_check_constraint(
        "ck_packages_status",
        "packages",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )
