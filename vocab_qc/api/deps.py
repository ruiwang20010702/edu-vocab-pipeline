"""FastAPI 依赖注入."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.services.qc_service import QcService
from vocab_qc.core.services.review_service import ReviewService


def get_db() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_review_service() -> ReviewService:
    return ReviewService()


def get_qc_service() -> QcService:
    return QcService()
