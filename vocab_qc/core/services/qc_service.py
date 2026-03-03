"""质检编排服务: 协调 Layer 1/2/3."""

from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models import (
    ContentItem,
    Meaning,
    Phonetic,
    QcStatus,
    ReviewReason,
    Word,
)
from vocab_qc.core.qc.runner import Layer1Runner
from vocab_qc.core.services.review_service import ReviewService


class QcService:
    """质检编排服务."""

    def __init__(self, review_service: Optional[ReviewService] = None):
        self.layer1_runner = Layer1Runner()
        self.review_service = review_service or ReviewService()

    def run_layer1(
        self,
        session: Session,
        scope: Optional[str] = None,
        dimension: Optional[str] = None,
    ) -> dict:
        """执行 Layer 1 算法校验.

        Args:
            scope: 范围筛选（如 "word_id:123"）
            dimension: 维度筛选（如 "chunk"）

        Returns:
            {"run_id": str, "total": int, "passed": int, "failed": int}
        """
        # 查询待校验的内容项
        query = session.query(ContentItem)
        if dimension:
            query = query.filter_by(dimension=dimension)
        if scope and scope.startswith("word_id:"):
            word_id = int(scope.split(":")[1])
            query = query.filter_by(word_id=word_id)

        items = query.all()
        if not items:
            return {"run_id": None, "total": 0, "passed": 0, "failed": 0}

        # 收集关联数据
        word_ids = {item.word_id for item in items}
        meaning_ids = {item.meaning_id for item in items if item.meaning_id}

        words = {w.id: w.word for w in session.query(Word).filter(Word.id.in_(word_ids)).all()}
        meanings = {m.id: m.definition for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all()}

        # 收集额外参数（音标、音节等）
        extra_kwargs = self._build_extra_kwargs(session, items)

        run_id = self.layer1_runner.run(session, items, words, meanings, extra_kwargs)

        # 统计
        passed = sum(1 for item in items if item.qc_status == QcStatus.LAYER1_PASSED.value)
        failed = sum(1 for item in items if item.qc_status == QcStatus.LAYER1_FAILED.value)

        return {"run_id": run_id, "total": len(items), "passed": passed, "failed": failed}

    def enqueue_failed_for_review(self, session: Session, run_id: str) -> int:
        """将 Layer 1 失败项加入审核队列.

        Returns:
            入队数量
        """
        failed_items = (
            session.query(ContentItem)
            .filter_by(qc_status=QcStatus.LAYER1_FAILED.value, last_qc_run_id=run_id)
            .all()
        )

        count = 0
        for item in failed_items:
            self.review_service.create_review_item(session, item, ReviewReason.LAYER1_FAILED, priority=10)
            count += 1

        session.flush()
        return count

    def enqueue_sampling(self, session: Session, run_id: str, sample_rate: float = 0.1) -> int:
        """将 Layer 1 通过项按比例抽样入审核队列.

        Returns:
            入队数量
        """
        import random

        passed_items = (
            session.query(ContentItem)
            .filter_by(qc_status=QcStatus.LAYER1_PASSED.value, last_qc_run_id=run_id)
            .all()
        )

        sample_size = max(1, int(len(passed_items) * sample_rate))
        sampled = random.sample(passed_items, min(sample_size, len(passed_items)))

        count = 0
        for item in sampled:
            self.review_service.create_review_item(session, item, ReviewReason.SAMPLING, priority=0)
            count += 1

        session.flush()
        return count

    def _build_extra_kwargs(self, session: Session, items: list[ContentItem]) -> dict[int, dict]:
        """为规则检查器构建额外参数（如音标、音节信息）."""
        extra = {}
        word_ids = {item.word_id for item in items}

        # 预加载音标和音节数据
        phonetics_by_word = {}
        for p in session.query(Phonetic).filter(Phonetic.word_id.in_(word_ids)).all():
            phonetics_by_word[p.word_id] = p

        for item in items:
            kwargs = {}
            phonetic = phonetics_by_word.get(item.word_id)
            if phonetic:
                kwargs["ipa"] = phonetic.ipa
                kwargs["syllables"] = phonetic.syllables

            # 为 meaning 维度传入 pos
            if item.dimension == "meaning" and item.meaning_id:
                meaning = session.query(Meaning).filter_by(id=item.meaning_id).first()
                if meaning:
                    kwargs["pos"] = meaning.pos

            extra[item.id] = kwargs

        return extra
