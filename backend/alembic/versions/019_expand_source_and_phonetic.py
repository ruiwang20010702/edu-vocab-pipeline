"""Source 新增 textbook_id/word_book_id/unit_id; Phonetic 拆分 ipa → ipa_uk/ipa_us + 新增 audio_url.

Revision ID: 019_expand_source_phonetic
Revises: 018_review_pending_uq
Create Date: 2026-03-25
"""

import sqlalchemy as sa
from alembic import op

revision = "019_expand_source_phonetic"
down_revision = "018_review_pending_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Source 表：新增教材结构化字段 ──
    op.add_column("sources", sa.Column("textbook_id", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("word_book_id", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("unit_id", sa.Integer(), nullable=True))

    # ── Phonetic 表：拆分 ipa → ipa_uk + ipa_us ──
    op.add_column("phonetics", sa.Column("ipa_uk", sa.String(200), nullable=True))
    op.add_column("phonetics", sa.Column("ipa_us", sa.String(200), nullable=True))
    op.add_column("phonetics", sa.Column("audio_url_uk", sa.String(500), nullable=True))
    op.add_column("phonetics", sa.Column("audio_url_us", sa.String(500), nullable=True))

    # 将旧 ipa 数据迁移到 ipa_uk（如果有数据的话）
    op.execute("UPDATE phonetics SET ipa_uk = ipa WHERE ipa IS NOT NULL AND ipa != ''")

    # 删除旧 ipa 列
    op.drop_column("phonetics", "ipa")


def downgrade() -> None:
    # 恢复旧 ipa 列
    op.add_column("phonetics", sa.Column("ipa", sa.String(200), nullable=True))
    op.execute("UPDATE phonetics SET ipa = ipa_uk WHERE ipa_uk IS NOT NULL")
    op.alter_column("phonetics", "ipa", nullable=False, server_default="")

    op.drop_column("phonetics", "audio_url_us")
    op.drop_column("phonetics", "audio_url_uk")
    op.drop_column("phonetics", "ipa_us")
    op.drop_column("phonetics", "ipa_uk")

    op.drop_column("sources", "unit_id")
    op.drop_column("sources", "word_book_id")
    op.drop_column("sources", "textbook_id")
