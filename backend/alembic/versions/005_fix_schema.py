"""Schema 修复: 时区、约束、索引、验证码字段.

Revision ID: 005_fix_schema
Revises: 004_add_prompts
Create Date: 2026-03-09
"""

import sqlalchemy as sa
from alembic import op

revision = "005_fix_schema"
down_revision = "004_add_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- C2: verification_codes 表修复 --
    op.add_column("verification_codes", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("verification_codes", "code", type_=sa.String(64), existing_type=sa.String(6))
    op.create_index("ix_verification_codes_expires", "verification_codes", ["expires_at"])

    # -- C3: 所有 DateTime 列加时区 (PostgreSQL: TIMESTAMP → TIMESTAMPTZ) --
    _tz_columns = [
        ("words", "created_at"),
        ("words", "updated_at"),
        ("phonetics", "created_at"),
        ("meanings", "created_at"),
        ("sources", "created_at"),
        ("content_items", "created_at"),
        ("content_items", "updated_at"),
        ("qc_runs", "started_at"),
        ("qc_runs", "finished_at"),
        ("qc_rule_results", "created_at"),
        ("retry_counters", "last_retry_at"),
        ("review_items", "resolved_at"),
        ("review_items", "created_at"),
        ("review_batches", "created_at"),
        ("review_batches", "completed_at"),
        ("packages", "created_at"),
        ("package_meanings", "created_at"),
        ("users", "created_at"),
        ("users", "last_login_at"),
        ("verification_codes", "created_at"),
        ("verification_codes", "expires_at"),
        ("prompts", "created_at"),
        ("prompts", "updated_at"),
        ("audit_logs_v2", "created_at"),
    ]
    for table, col in _tz_columns:
        op.alter_column(table, col, type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())

    # -- M2: Phonetic 唯一约束 --
    op.create_unique_constraint("uq_phonetics_word_id", "phonetics", ["word_id"])

    # -- M4: QcRuleResult.meaning_id 索引 --
    op.create_index("ix_qc_rule_results_meaning_id", "qc_rule_results", ["meaning_id"])

    # -- M5: PackageMeaning 复合唯一约束 --
    op.create_unique_constraint("uq_package_meanings_pkg_meaning", "package_meanings", ["package_id", "meaning_id"])

    # -- M6: RetryCounter 外键级联 (需要重建外键) --
    op.drop_constraint("retry_counters_word_id_fkey", "retry_counters", type_="foreignkey")
    op.create_foreign_key(
        "retry_counters_word_id_fkey", "retry_counters", "words",
        ["word_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("retry_counters_meaning_id_fkey", "retry_counters", type_="foreignkey")
    op.create_foreign_key(
        "retry_counters_meaning_id_fkey", "retry_counters", "meanings",
        ["meaning_id"], ["id"], ondelete="CASCADE",
    )

    # -- M1: 状态字段 CHECK 约束 --
    op.create_check_constraint(
        "ck_review_items_status", "review_items",
        "status IN ('pending', 'in_progress', 'resolved')",
    )
    op.create_check_constraint(
        "ck_review_batches_status", "review_batches",
        "status IN ('in_progress', 'completed')",
    )
    op.create_check_constraint(
        "ck_packages_status", "packages",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )

    # -- L3 + L4: AuditLogV2 entity_id 类型 + 复合索引 --
    op.alter_column("audit_logs_v2", "entity_id", type_=sa.String(36), existing_type=sa.Integer())
    op.create_index("ix_audit_entity", "audit_logs_v2", ["entity_type", "entity_id"])

    # -- L6: Prompt 活跃唯一索引 (PostgreSQL 部分唯一索引) --
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_dim "
        "ON prompts (category, dimension) WHERE is_active = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_prompts_active_dim")
    op.drop_index("ix_audit_entity", table_name="audit_logs_v2")
    op.alter_column("audit_logs_v2", "entity_id", type_=sa.Integer(), existing_type=sa.String(36))

    op.drop_constraint("ck_packages_status", "packages", type_="check")
    op.drop_constraint("ck_review_batches_status", "review_batches", type_="check")
    op.drop_constraint("ck_review_items_status", "review_items", type_="check")

    op.drop_constraint("retry_counters_meaning_id_fkey", "retry_counters", type_="foreignkey")
    op.create_foreign_key("retry_counters_meaning_id_fkey", "retry_counters", "meanings", ["meaning_id"], ["id"])
    op.drop_constraint("retry_counters_word_id_fkey", "retry_counters", type_="foreignkey")
    op.create_foreign_key("retry_counters_word_id_fkey", "retry_counters", "words", ["word_id"], ["id"])

    op.drop_constraint("uq_package_meanings_pkg_meaning", "package_meanings", type_="unique")
    op.drop_index("ix_qc_rule_results_meaning_id", table_name="qc_rule_results")
    op.drop_constraint("uq_phonetics_word_id", "phonetics", type_="unique")

    _tz_columns = [
        ("words", "created_at"),
        ("words", "updated_at"),
        ("phonetics", "created_at"),
        ("meanings", "created_at"),
        ("sources", "created_at"),
        ("content_items", "created_at"),
        ("content_items", "updated_at"),
        ("qc_runs", "started_at"),
        ("qc_runs", "finished_at"),
        ("qc_rule_results", "created_at"),
        ("retry_counters", "last_retry_at"),
        ("review_items", "resolved_at"),
        ("review_items", "created_at"),
        ("review_batches", "created_at"),
        ("review_batches", "completed_at"),
        ("packages", "created_at"),
        ("package_meanings", "created_at"),
        ("users", "created_at"),
        ("users", "last_login_at"),
        ("verification_codes", "created_at"),
        ("verification_codes", "expires_at"),
        ("prompts", "created_at"),
        ("prompts", "updated_at"),
        ("audit_logs_v2", "created_at"),
    ]
    for table, col in reversed(_tz_columns):
        op.alter_column(table, col, type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))

    op.drop_index("ix_verification_codes_expires", table_name="verification_codes")
    op.alter_column("verification_codes", "code", type_=sa.String(6), existing_type=sa.String(64))
    op.drop_column("verification_codes", "attempts")
