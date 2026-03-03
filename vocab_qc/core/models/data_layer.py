"""数据层模型: Word, Phonetic, Meaning, Source."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vocab_qc.core.db import Base


class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    phonetics: Mapped[list["Phonetic"]] = relationship(back_populates="word_rel", cascade="all, delete-orphan")
    meanings: Mapped[list["Meaning"]] = relationship(back_populates="word_rel", cascade="all, delete-orphan")
    content_items: Mapped[list["ContentItem"]] = relationship(back_populates="word_rel")

    def __repr__(self) -> str:
        return f"<Word id={self.id} word={self.word!r}>"


class Phonetic(Base):
    __tablename__ = "phonetics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False, index=True)
    ipa: Mapped[str] = mapped_column(String(200), nullable=False)
    syllables: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    word_rel: Mapped["Word"] = relationship(back_populates="phonetics")

    def __repr__(self) -> str:
        return f"<Phonetic id={self.id} ipa={self.ipa!r}>"


class Meaning(Base):
    __tablename__ = "meanings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False, index=True)
    pos: Mapped[str] = mapped_column(String(20), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    word_rel: Mapped["Word"] = relationship(back_populates="meanings")
    sources: Mapped[list["Source"]] = relationship(back_populates="meaning_rel", cascade="all, delete-orphan")
    content_items: Mapped[list["ContentItem"]] = relationship(back_populates="meaning_rel")

    def __repr__(self) -> str:
        return f"<Meaning id={self.id} pos={self.pos!r} def={self.definition!r}>"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meaning_id: Mapped[int] = mapped_column(ForeignKey("meanings.id"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    meaning_rel: Mapped["Meaning"] = relationship(back_populates="sources")

    def __repr__(self) -> str:
        return f"<Source id={self.id} name={self.source_name!r}>"


# 避免循环引入，此处仅做类型注释导入
from vocab_qc.core.models.content_layer import ContentItem  # noqa: E402, F401
