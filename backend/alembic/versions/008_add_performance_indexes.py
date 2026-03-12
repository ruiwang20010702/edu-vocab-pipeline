"""新增性能优化索引.

Revision ID: 008_add_performance_indexes
Revises: 007_add_ai_error_logs
Create Date: 2026-03-12
"""

from alembic import op

revision = "008_add_performance_indexes"
down_revision = "007_add_ai_error_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # QcRuleResult: 覆盖 (content_item_id, run_id, passed) 的高频查询
    op.create_index(
        "ix_qc_rule_results_item_run_passed",
        "qc_rule_results",
        ["content_item_id", "run_id", "passed"],
    )
    # ContentItem: 覆盖按 word + dimension + qc_status 的过滤查询
    op.create_index(
        "ix_content_items_word_dim_status",
        "content_items",
        ["word_id", "dimension", "qc_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_items_word_dim_status", table_name="content_items")
    op.drop_index("ix_qc_rule_results_item_run_passed", table_name="qc_rule_results")
