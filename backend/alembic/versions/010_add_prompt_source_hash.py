"""新增 Prompt source/file_hash 字段.

Revision ID: 010_add_prompt_source_hash
Revises: 009_add_last_qc_run_id_index
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "010_add_prompt_source_hash"
down_revision = "009_add_last_qc_run_id_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("source", sa.String(20), nullable=False, server_default="file"))
    op.add_column("prompts", sa.Column("file_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("prompts", "file_hash")
    op.drop_column("prompts", "source")
