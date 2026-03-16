"""批次派发并发场景测试."""

from sqlalchemy.orm import Session
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Word
from vocab_qc.core.models.enums import BatchStatus, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem
from vocab_qc.core.models.user import User
from vocab_qc.core.services.batch_service import assign_batch


def _create_users(session: Session) -> tuple[User, User]:
    """创建两个审核员."""
    user1 = User(email="reviewer1@test.com", name="Reviewer1", role="reviewer")
    user2 = User(email="reviewer2@test.com", name="Reviewer2", role="reviewer")
    session.add_all([user1, user2])
    session.flush()
    return user1, user2


def _create_review_items(
    session: Session,
    word_count: int,
    items_per_word: int = 2,
) -> list[ReviewItem]:
    """创建指定数量的 Word → Meaning → ContentItem → ReviewItem 链条.

    每个 word 生成 items_per_word 条 pending ReviewItem.
    """
    review_items: list[ReviewItem] = []
    for i in range(word_count):
        word = Word(word=f"word_{i}")
        session.add(word)
        session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition=f"释义_{i}")
        session.add(meaning)
        session.flush()

        for j in range(items_per_word):
            ci = ContentItem(
                word_id=word.id,
                meaning_id=meaning.id,
                dimension="chunk" if j % 2 == 0 else "sentence",
                content=f"content_{i}_{j}",
            )
            session.add(ci)
            session.flush()

            ri = ReviewItem(
                content_item_id=ci.id,
                word_id=word.id,
                meaning_id=meaning.id,
                dimension=ci.dimension,
                reason="layer1_failed",
                status=ReviewStatus.PENDING.value,
            )
            session.add(ri)
            review_items.append(ri)

    session.flush()
    return review_items


class TestAssignBatchConcurrent:
    """assign_batch 并发场景测试."""

    def test_two_users_simultaneous_only_enough_for_one(self, db_session: Session):
        """只有 3 个词，batch_size=3，第一个用户拿走后第二个用户应得到 None."""
        user1, user2 = _create_users(db_session)
        _create_review_items(db_session, word_count=3)

        batch1 = assign_batch(db_session, user1.id, batch_size=3)
        batch2 = assign_batch(db_session, user2.id, batch_size=3)

        assert batch1 is not None
        assert batch1.user_id == user1.id
        assert batch1.status == BatchStatus.IN_PROGRESS.value
        assert batch1.word_count == 3

        assert batch2 is None

    def test_same_user_gets_existing_batch(self, db_session: Session):
        """同一用户重复请求时，应返回已有的 IN_PROGRESS 批次而非新建."""
        user1, _ = _create_users(db_session)
        _create_review_items(db_session, word_count=5)

        batch_first = assign_batch(db_session, user1.id, batch_size=3)
        batch_second = assign_batch(db_session, user1.id, batch_size=3)

        assert batch_first is not None
        assert batch_second is not None
        assert batch_first.id == batch_second.id

    def test_batch_items_exclusive_no_overlap(self, db_session: Session):
        """两个用户各领一批，word_id 不应有重叠."""
        user1, user2 = _create_users(db_session)
        _create_review_items(db_session, word_count=6)

        batch1 = assign_batch(db_session, user1.id, batch_size=3)
        batch2 = assign_batch(db_session, user2.id, batch_size=3)

        assert batch1 is not None
        assert batch2 is not None

        word_ids_1 = {
            ri.word_id
            for ri in db_session.query(ReviewItem).filter_by(batch_id=batch1.id).all()
        }
        word_ids_2 = {
            ri.word_id
            for ri in db_session.query(ReviewItem).filter_by(batch_id=batch2.id).all()
        }

        assert len(word_ids_1) == 3
        assert len(word_ids_2) == 3
        assert word_ids_1.isdisjoint(word_ids_2), (
            f"批次间 word_id 存在重叠: {word_ids_1 & word_ids_2}"
        )

    def test_empty_pool_returns_none(self, db_session: Session):
        """没有 pending ReviewItem 时应返回 None."""
        user1, _ = _create_users(db_session)
        # 不创建任何 ReviewItem

        result = assign_batch(db_session, user1.id, batch_size=10)

        assert result is None
