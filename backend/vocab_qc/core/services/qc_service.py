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
from vocab_qc.core.models.enums import QC_TERMINAL_STATUSES
from vocab_qc.core.models.quality_layer import QcRuleResult, QcRun
from vocab_qc.core.qc.layer2.runner import Layer2Runner
from vocab_qc.core.qc.runner import Layer1Runner
from vocab_qc.core.services.review_service import ReviewService


class QcService:
    """质检编排服务."""

    def __init__(self, review_service: Optional[ReviewService] = None):
        self.layer1_runner = Layer1Runner()
        self.layer2_runner = Layer2Runner()
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
        # 查询待校验的内容项（排除终态：APPROVED / REJECTED）
        query = session.query(ContentItem).filter(
            ContentItem.qc_status.notin_(QC_TERMINAL_STATUSES)
        )
        if dimension:
            query = query.filter_by(dimension=dimension)
        if scope and scope.startswith("word_id:"):
            try:
                word_id = int(scope.split(":")[1])
            except (ValueError, IndexError):
                raise ValueError(f"无效的 scope 格式: {scope}，预期格式为 'word_id:<数字>'")
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

    def run_layer2(
        self,
        session: Session,
        scope: Optional[str] = None,
        dimension: Optional[str] = None,
    ) -> dict:
        """执行 Layer 2 AI 语义校验（仅针对 Layer 1 通过项）.

        Returns:
            {"run_id": str, "total": int, "passed": int, "failed": int}
        """
        query = session.query(ContentItem).filter_by(qc_status=QcStatus.LAYER1_PASSED.value)
        if dimension:
            query = query.filter_by(dimension=dimension)
        if scope and scope.startswith("word_id:"):
            try:
                word_id = int(scope.split(":")[1])
            except (ValueError, IndexError):
                raise ValueError(f"无效的 scope 格式: {scope}，预期格式为 'word_id:<数字>'")
            query = query.filter_by(word_id=word_id)

        items = query.all()
        if not items:
            return {"run_id": None, "total": 0, "passed": 0, "failed": 0}

        word_ids = {item.word_id for item in items}
        meaning_ids = {item.meaning_id for item in items if item.meaning_id}

        word_texts = {w.id: w.word for w in session.query(Word).filter(Word.id.in_(word_ids)).all()}
        meaning_texts = {m.id: m.definition for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all()}

        extra_kwargs = self._build_extra_kwargs(session, items)

        run_id = self.layer2_runner.run(session, items, word_texts, meaning_texts, extra_kwargs=extra_kwargs)

        passed = sum(1 for item in items if item.qc_status == QcStatus.LAYER2_PASSED.value)
        failed = sum(1 for item in items if item.qc_status == QcStatus.LAYER2_FAILED.value)

        return {"run_id": run_id, "total": len(items), "passed": passed, "failed": failed}

    def enqueue_layer2_failed_for_review(self, session: Session, run_id: str) -> int:
        """将 Layer 2 失败项加入审核队列."""
        failed_items = (
            session.query(ContentItem)
            .filter_by(qc_status=QcStatus.LAYER2_FAILED.value, last_qc_run_id=run_id)
            .all()
        )
        count = 0
        for item in failed_items:
            self.review_service.create_review_item(session, item, ReviewReason.LAYER2_FAILED, priority=5)
            count += 1
        session.flush()
        return count

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

        # 批量预加载 meaning pos（避免 N+1）
        meaning_ids = {item.meaning_id for item in items if item.meaning_id and item.dimension == "meaning"}
        meanings_pos = {}
        if meaning_ids:
            for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all():
                meanings_pos[m.id] = m.pos

        for item in items:
            kwargs: dict = {"content_cn": item.content_cn or ""}
            phonetic = phonetics_by_word.get(item.word_id)
            if phonetic:
                kwargs["ipa"] = phonetic.ipa
                kwargs["syllables"] = phonetic.syllables

            # 为 meaning 维度传入 pos
            if item.dimension == "meaning" and item.meaning_id:
                pos = meanings_pos.get(item.meaning_id)
                if pos:
                    kwargs["pos"] = pos

            extra[item.id] = kwargs

        return extra

    # ---- 查询方法（供路由层调用，避免路由直接操作 ORM） ----

    @staticmethod
    def get_run(session: Session, run_id: str) -> QcRun | None:
        return session.query(QcRun).filter_by(id=run_id).first()

    @staticmethod
    def get_run_results(
        session: Session,
        run_id: str,
        passed: bool | None = None,
        rule_id: str | None = None,
    ) -> list[QcRuleResult]:
        query = session.query(QcRuleResult).filter_by(run_id=run_id)
        if passed is not None:
            query = query.filter_by(passed=passed)
        if rule_id:
            query = query.filter_by(rule_id=rule_id)
        return query.all()

    @staticmethod
    def get_summary(session: Session, run_id: str | None = None) -> list[dict]:
        from sqlalchemy import case, func

        query = session.query(
            QcRuleResult.rule_id,
            QcRuleResult.dimension,
            func.count().label("total"),
            func.count(case((QcRuleResult.passed == True, 1))).label("passed_count"),  # noqa: E712
        ).group_by(QcRuleResult.rule_id, QcRuleResult.dimension)

        if run_id:
            query = query.filter(QcRuleResult.run_id == run_id)

        results = []
        for row in query.all():
            total = row.total
            passed = int(row.passed_count or 0)
            results.append({
                "rule_id": row.rule_id,
                "dimension": row.dimension,
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            })
        return results
