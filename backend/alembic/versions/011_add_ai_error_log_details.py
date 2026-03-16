"""新增 AiErrorLog 诊断字段: http_status_code, response_body, elapsed_ms.

Revision ID: 011_add_ai_error_log_details
Revises: 010_add_prompt_source_hash
Create Date: 2026-03-16
"""

import sqlalchemy as sa
from alembic import op

revision = "011_add_ai_error_log_details"
down_revision = "010_add_prompt_source_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_error_logs", sa.Column("http_status_code", sa.Integer(), nullable=True))
    op.add_column("ai_error_logs", sa.Column("response_body", sa.Text(), nullable=True))
    op.add_column("ai_error_logs", sa.Column("elapsed_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_error_logs", "elapsed_ms")
    op.drop_column("ai_error_logs", "response_body")
    op.drop_column("ai_error_logs", "http_status_code")
