"""sources 表 textbook_id/word_book_id/unit_id 从 INTEGER 改为 VARCHAR(50)。

原始设计假定 ID 为纯数字，实际数据为字符串格式（如 TB001, WB001, U01），
导致 _safe_int 转换失败、Source 记录从未创建。

Revision ID: 020_source_ids_to_varchar
Revises: 019_expand_source_phonetic
Create Date: 2026-03-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_source_ids_to_varchar"
down_revision: Union[str, None] = "019_expand_source_phonetic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sources", "textbook_id",
        existing_type=sa.Integer(),
        type_=sa.String(50),
        existing_nullable=True,
        postgresql_using="textbook_id::varchar",
    )
    op.alter_column(
        "sources", "word_book_id",
        existing_type=sa.Integer(),
        type_=sa.String(50),
        existing_nullable=True,
        postgresql_using="word_book_id::varchar",
    )
    op.alter_column(
        "sources", "unit_id",
        existing_type=sa.Integer(),
        type_=sa.String(50),
        existing_nullable=True,
        postgresql_using="unit_id::varchar",
    )


def downgrade() -> None:
    op.alter_column(
        "sources", "textbook_id",
        existing_type=sa.String(50),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="textbook_id::integer",
    )
    op.alter_column(
        "sources", "word_book_id",
        existing_type=sa.String(50),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="word_book_id::integer",
    )
    op.alter_column(
        "sources", "unit_id",
        existing_type=sa.String(50),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="unit_id::integer",
    )
