"""新增 review_batches 表 + ReviewItem 批次字段.

Revision ID: 002_add_batch
Revises: 001_add_users
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa

revision = "002_add_batch"
down_revision = "001_add_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_batches_user_id", "review_batches", ["user_id"])

    op.add_column("review_items", sa.Column("batch_id", sa.Integer(), sa.ForeignKey("review_batches.id"), nullable=True))
    op.add_column("review_items", sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_review_items_batch_id", "review_items", ["batch_id"])
    op.create_index("ix_review_items_assigned_to_id", "review_items", ["assigned_to_id"])


def downgrade() -> None:
    op.drop_index("ix_review_items_assigned_to_id", "review_items")
    op.drop_index("ix_review_items_batch_id", "review_items")
    op.drop_column("review_items", "assigned_to_id")
    op.drop_column("review_items", "batch_id")
    op.drop_table("review_batches")
