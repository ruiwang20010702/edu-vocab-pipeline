"""词包层模型: Package, PackageMeaning."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from vocab_qc.core.db import Base


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_packages_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    total_words: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_words: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Package id={self.id} name={self.name!r}>"


class PackageMeaning(Base):
    __tablename__ = "package_meanings"
    __table_args__ = (
        UniqueConstraint("package_id", "meaning_id", name="uq_package_meanings_pkg_meaning"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"), nullable=False, index=True)
    meaning_id: Mapped[int] = mapped_column(ForeignKey("meanings.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PackageMeaning pkg={self.package_id} meaning={self.meaning_id}>"
