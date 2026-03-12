"""新增 last_qc_run_id 索引.

Revision ID: 009_add_last_qc_run_id_index
Revises: 008_add_performance_indexes
Create Date: 2026-03-12
"""

from alembic import op

revision = "009_add_last_qc_run_id_index"
down_revision = "008_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # P-M2: 多处查询依赖 last_qc_run_id 过滤旧质检记录
    op.create_index(
        "ix_content_items_last_qc_run_id",
        "content_items",
        ["last_qc_run_id"],
    )
    op.create_index(
        "ix_qc_rule_results_run_id",
        "qc_rule_results",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_qc_rule_results_run_id", table_name="qc_rule_results")
    op.drop_index("ix_content_items_last_qc_run_id", table_name="content_items")
