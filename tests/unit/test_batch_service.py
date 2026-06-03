"""批次派发服务单元测试."""

import pytest
from sqlalchemy.orm import Session
from vocab_qc.core.config import settings
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, ReviewItem, ReviewReason, Word
from vocab_qc.core.models.batch_layer import ReviewBatch
from vocab_qc.core.models.enums import BatchStatus, QcStatus, ReviewStatus
from vocab_qc.core.models.user import User
from vocab_qc.core.services import batch_service
from vocab_qc.core.services.review_service import ReviewService


def _create_user(db: Session, email: str = "u1@test.com", name: str = "User1", role: str = "reviewer") -> User:
    user = User(email=email, name=name, role=role)
    db.add(user)
    db.flush()
    return user


def _create_word_with_reviews(db: Session, word_text: str, n_items: int = 2) -> tuple[Word, list[ReviewItem]]:
    """创建一个词并生成 n 个 pending ReviewItem。"""
    word = Word(word=word_text)
    db.add(word)
    db.flush()

    phonetic = Phonetic(word_id=word.id, ipa_uk=f"/{word_text}/", syllables=word_text)
    meaning = Meaning(word_id=word.id, pos="n.", definition=f"{word_text}的意思")
    db.add_all([phonetic, meaning])
    db.flush()

    service = ReviewService()
    reviews = []
    for i in range(n_items):
        dim = "chunk" if i % 2 == 0 else "sentence"
        content = ContentItem(word_id=word.id, meaning_id=meaning.id, dimension=dim, content=f"{word_text} content {i}")
        db.add(content)
        db.flush()
        review = service.create_review_item(db, content, ReviewReason.LAYER1_FAILED)
        reviews.append(review)

    return word, reviews


class TestAssignBatch:
    def test_assigns_batch(self, db_session: Session):
        user = _create_user(db_session)
        _create_word_with_reviews(db_session, "apple")
        _create_word_with_reviews(db_session, "banana")

        batch = batch_service.assign_batch(db_session, user.id, batch_size=10)
        assert batch is not None
        assert batch.word_count == 2
        assert batch.status == BatchStatus.IN_PROGRESS.value

    def test_returns_existing_batch(self, db_session: Session):
        user = _create_user(db_session)
        _create_word_with_reviews(db_session, "apple")

        batch1 = batch_service.assign_batch(db_session, user.id)
        batch2 = batch_service.assign_batch(db_session, user.id)
        assert batch1.id == batch2.id

    def test_empty_pool_returns_none(self, db_session: Session):
        user = _create_user(db_session)
        batch = batch_service.assign_batch(db_session, user.id)
        assert batch is None

    def test_assigns_items_to_user(self, db_session: Session):
        user = _create_user(db_session)
        _, reviews = _create_word_with_reviews(db_session, "cherry")

        batch = batch_service.assign_batch(db_session, user.id)
        for r in reviews:
            db_session.refresh(r)
            assert r.assigned_to_id == user.id
            assert r.batch_id == batch.id

    def test_batch_size_limit(self, db_session: Session):
        user = _create_user(db_session)
        for i in range(5):
            _create_word_with_reviews(db_session, f"word{i}")

        batch = batch_service.assign_batch(db_session, user.id, batch_size=3)
        assert batch.word_count == 3


class TestNoOverlap:
    def test_two_users_no_overlap(self, db_session: Session):
        """两个用户同时领取不会拿到重叠的词。"""
        user1 = _create_user(db_session, "u1@test.com", "User1")
        user2 = _create_user(db_session, "u2@test.com", "User2")

        for i in range(6):
            _create_word_with_reviews(db_session, f"word{i}")

        batch1 = batch_service.assign_batch(db_session, user1.id, batch_size=3)
        batch2 = batch_service.assign_batch(db_session, user2.id, batch_size=3)

        assert batch1 is not None
        assert batch2 is not None

        # 获取各自批次的 word_id
        data1 = batch_service.get_batch_words(db_session, batch1.id)
        data2 = batch_service.get_batch_words(db_session, batch2.id)
        words1 = set(data1["words"].keys())
        words2 = set(data2["words"].keys())

        assert words1.isdisjoint(words2), f"重叠词: {words1 & words2}"


class TestSkipWord:
    def test_skip_releases_items(self, db_session: Session):
        user = _create_user(db_session)
        word, reviews = _create_word_with_reviews(db_session, "date")
        batch = batch_service.assign_batch(db_session, user.id)

        batch_service.skip_word(db_session, batch.id, word.id, user.id)

        for r in reviews:
            db_session.refresh(r)
            assert r.batch_id is None
            assert r.assigned_to_id is None

    def test_skip_wrong_user_raises(self, db_session: Session):
        user1 = _create_user(db_session, "u1@test.com", "User1")
        user2 = _create_user(db_session, "u2@test.com", "User2")
        word, _ = _create_word_with_reviews(db_session, "elderberry")
        batch = batch_service.assign_batch(db_session, user1.id)

        with pytest.raises(ValueError, match="无权操作"):
            batch_service.skip_word(db_session, batch.id, word.id, user2.id)


class TestCompleteBatch:
    def test_manual_complete(self, db_session: Session):
        user = _create_user(db_session)
        _create_word_with_reviews(db_session, "fig")
        batch = batch_service.assign_batch(db_session, user.id)

        result = batch_service.complete_batch(db_session, batch.id, user.id)
        assert result.status == BatchStatus.COMPLETED.value
        assert result.completed_at is not None


class TestAutoComplete:
    def test_all_reviewed_auto_completes(self, db_session: Session):
        """所有词审完后批次自动完成。"""
        user = _create_user(db_session)
        _, reviews = _create_word_with_reviews(db_session, "grape", n_items=2)
        batch = batch_service.assign_batch(db_session, user.id)

        service = ReviewService()
        for r in reviews:
            service.approve(db_session, r.id, reviewer="Admin")

        db_session.refresh(batch)
        assert batch.status == BatchStatus.COMPLETED.value
        assert batch.reviewed_count == 1


class TestConcurrencyCheck:
    def test_approve_resolved_item_raises(self, db_session: Session):
        user = _create_user(db_session)
        _, reviews = _create_word_with_reviews(db_session, "honeydew")
        batch_service.assign_batch(db_session, user.id)

        service = ReviewService()
        service.approve(db_session, reviews[0].id, reviewer="Admin")

        with pytest.raises(ValueError, match="已被处理"):
            service.approve(db_session, reviews[0].id, reviewer="Admin")

    def test_approve_other_users_item_raises(self, db_session: Session):
        user1 = _create_user(db_session, "u1@test.com", "User1")
        user2 = _create_user(db_session, "u2@test.com", "User2")
        _, reviews = _create_word_with_reviews(db_session, "icefruit")
        batch_service.assign_batch(db_session, user1.id)

        service = ReviewService()
        with pytest.raises(ValueError, match="已分配给其他审核员"):
            service.approve(db_session, reviews[0].id, reviewer="User2", user_id=user2.id)


class TestProcessingLock:
    """生产中锁：Package 为 processing 时，其关联词不被领取。"""

    def test_processing_words_excluded(self, db_session: Session):
        """正在生产的 Package 关联的 word 不应被 assign_batch 领取。"""
        from vocab_qc.core.models.package_layer import Package, PackageWord

        user = _create_user(db_session)

        # 创建一个 processing 状态的 Package，关联 word "mango"
        word_mango, reviews_mango = _create_word_with_reviews(db_session, "mango")
        pkg = Package(name="processing_pkg", status="processing", total_words=1)
        db_session.add(pkg)
        db_session.flush()
        db_session.add(PackageWord(package_id=pkg.id, word_id=word_mango.id))
        db_session.flush()

        # 创建一个不在任何 Package 中的 word "kiwi"
        _create_word_with_reviews(db_session, "kiwi")

        batch = batch_service.assign_batch(db_session, user.id, batch_size=10)
        assert batch is not None
        # 只应领取 kiwi，不应领取 mango
        assert batch.word_count == 1
        data = batch_service.get_batch_words(db_session, batch.id)
        assigned_word_ids = set(data["words"].keys())
        assert word_mango.id not in assigned_word_ids

    def test_completed_package_words_available(self, db_session: Session):
        """已完成的 Package 关联的 word 应该可以被领取。"""
        from vocab_qc.core.models.package_layer import Package, PackageWord

        user = _create_user(db_session)

        word, _ = _create_word_with_reviews(db_session, "papaya")
        pkg = Package(name="completed_pkg", status="completed", total_words=1)
        db_session.add(pkg)
        db_session.flush()
        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))
        db_session.flush()

        batch = batch_service.assign_batch(db_session, user.id, batch_size=10)
        assert batch is not None
        assert batch.word_count == 1


def _create_mnemonic_orphan(
    db: Session, word_text: str, *, qc_status: str, content: str = "",
    retry_count: int = 0, dimension: str = "mnemonic_word_in_word",
) -> tuple[Word, ContentItem, ReviewItem]:
    """创建一个助记 ContentItem（可设 rejected/空内容/达上限）+ 其 pending ReviewItem。"""
    word = Word(word=word_text)
    db.add(word)
    db.flush()
    meaning = Meaning(word_id=word.id, pos="v.", definition=f"{word_text} def")
    db.add(meaning)
    db.flush()
    ci = ContentItem(
        word_id=word.id, meaning_id=meaning.id, dimension=dimension,
        content=content, qc_status=qc_status, retry_count=retry_count,
    )
    db.add(ci)
    db.flush()
    review = ReviewService().create_review_item(db, ci, ReviewReason.LAYER2_FAILED)
    return word, ci, review


def _put_review_in_batch(db: Session, user: User, review: ReviewItem) -> ReviewBatch:
    """手动把 pending review 挂进一个 in_progress 批次，模拟根治前已打包孤儿的存量批次。"""
    batch = ReviewBatch(
        user_id=user.id, status=BatchStatus.IN_PROGRESS.value,
        word_count=1, reviewed_count=0,
    )
    db.add(batch)
    db.flush()
    review.batch_id = batch.id
    review.assigned_to_id = user.id
    db.flush()
    return batch


class TestDeadlockOrphanCleanup:
    """死锁孤儿自愈：rejected 或 (空内容+达上限) 的 pending review 应被解除，
    使卡死批次完结；可恢复项（空但未达上限）不应误清。"""

    def test_resolves_rejected_orphan_and_completes_batch(self, db_session: Session):
        user = _create_user(db_session)
        _, _, review = _create_mnemonic_orphan(
            db_session, "confine", qc_status=QcStatus.REJECTED.value, content="",
        )
        batch = _put_review_in_batch(db_session, user, review)

        n = batch_service._resolve_deadlocked_orphans(db_session, batch.id)
        assert n == 1
        db_session.refresh(review)
        assert review.status == ReviewStatus.RESOLVED.value
        db_session.refresh(batch)
        assert batch.status == BatchStatus.COMPLETED.value

    def test_resolves_empty_at_limit_orphan(self, db_session: Session):
        user = _create_user(db_session)
        _, _, review = _create_mnemonic_orphan(
            db_session, "confine2", qc_status=QcStatus.LAYER2_FAILED.value,
            content="", retry_count=settings.ai_max_retries,
        )
        batch = _put_review_in_batch(db_session, user, review)
        n = batch_service._resolve_deadlocked_orphans(db_session, batch.id)
        assert n == 1
        db_session.refresh(review)
        assert review.status == ReviewStatus.RESOLVED.value

    def test_keeps_recoverable_orphan(self, db_session: Session):
        """content='' 但 retry<max 且非 rejected → 可重生，不应被清。"""
        user = _create_user(db_session)
        _, _, review = _create_mnemonic_orphan(
            db_session, "confine3", qc_status=QcStatus.LAYER1_FAILED.value,
            content="", retry_count=0,
        )
        batch = batch_service.assign_batch(db_session, user.id)
        n = batch_service._resolve_deadlocked_orphans(db_session, batch.id)
        assert n == 0
        db_session.refresh(review)
        assert review.status == ReviewStatus.PENDING.value

    def test_assign_batch_self_heals_deadlocked_batch(self, db_session: Session):
        """存量卡死批次（根治前已打包孤儿）在重新 assign 时由 existing 分支自愈完结。"""
        user = _create_user(db_session)
        _, _, review = _create_mnemonic_orphan(
            db_session, "confine4", qc_status=QcStatus.REJECTED.value, content="",
        )
        batch1 = _put_review_in_batch(db_session, user, review)
        # 再次 assign：existing 分支应先自愈 batch1 → pending 清零 → 自动完结
        batch_service.assign_batch(db_session, user.id)
        db_session.refresh(batch1)
        assert batch1.status == BatchStatus.COMPLETED.value

    def test_repair_skips_empty_at_limit(self, db_session: Session):
        """_repair_orphan_failed_items 不给 content='' AND retry>=max 的项补 review。"""
        word = Word(word="confine5")
        db_session.add(word)
        db_session.flush()
        meaning = Meaning(word_id=word.id, pos="v.", definition="x")
        db_session.add(meaning)
        db_session.flush()
        ci = ContentItem(
            word_id=word.id, meaning_id=meaning.id, dimension="mnemonic_word_in_word",
            content="", qc_status=QcStatus.LAYER2_FAILED.value,
            retry_count=settings.ai_max_retries,
        )
        db_session.add(ci)
        db_session.flush()

        batch_service._repair_orphan_failed_items(db_session)
        cnt = (
            db_session.query(ReviewItem)
            .filter_by(content_item_id=ci.id, status=ReviewStatus.PENDING.value)
            .count()
        )
        assert cnt == 0

    def test_assign_does_not_pack_deadlock_orphan_into_new_batch(self, db_session: Session):
        """根治：领取新批次前全局自愈，死锁孤儿不应被打包进新批次。

        旧逻辑只清理 existing 旧批次的孤儿，新建批次时仍按 status=pending 捞取，
        会把 content='' 且达上限的孤儿一并打包进新批次，卡住审核员（点开无内容）。
        """
        user = _create_user(db_session)
        _, _, orphan_review = _create_mnemonic_orphan(
            db_session, "calculus", qc_status=QcStatus.LAYER2_FAILED.value,
            content="", retry_count=settings.ai_max_retries,
        )
        batch = batch_service.assign_batch(db_session, user.id)
        # 仅有死锁孤儿、无真任务 → 领取前被全局自愈，不应领到批次
        assert batch is None
        db_session.refresh(orphan_review)
        assert orphan_review.status == ReviewStatus.RESOLVED.value
        assert orphan_review.batch_id is None

    def test_assign_packs_real_task_and_resolves_orphan(self, db_session: Session):
        """混合场景：有内容的真待审项正常领取，死锁孤儿同时被自愈、不混入批次。"""
        user = _create_user(db_session)
        _, _, real_review = _create_mnemonic_orphan(
            db_session, "decoration", qc_status=QcStatus.LAYER2_FAILED.value,
            content="some real content", retry_count=settings.ai_max_retries,
        )
        _, _, orphan_review = _create_mnemonic_orphan(
            db_session, "calculus2", qc_status=QcStatus.LAYER2_FAILED.value,
            content="", retry_count=settings.ai_max_retries,
        )
        batch = batch_service.assign_batch(db_session, user.id)
        assert batch is not None
        # 真任务（content 非空）正常进批次
        db_session.refresh(real_review)
        assert real_review.batch_id == batch.id
        assert real_review.status == ReviewStatus.PENDING.value
        # 死锁孤儿被自愈，不进批次
        db_session.refresh(orphan_review)
        assert orphan_review.status == ReviewStatus.RESOLVED.value
        assert orphan_review.batch_id is None
