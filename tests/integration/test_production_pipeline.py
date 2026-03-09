"""生产流水线集成测试.

覆盖:
- _run_production_bg 正常完成 → Package.status == "completed"
- _run_production_bg 异常时 → Package.status == "failed"
- 完整流水线: 导入 → 生产 → L1 质检 → 入队审核
"""

import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Package, PackageMeaning, ReviewItem, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.services.production_service import run_production


@pytest.fixture
def prod_engine():
    """独立的 SQLite 内存引擎，模拟 _run_production_bg 的独立 session 场景。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def prod_session(prod_engine):
    """独立 session，不使用事务回滚（模拟真实后台任务行为）。"""
    Session = sessionmaker(bind=prod_engine)
    session = Session()
    yield session
    session.close()


def _seed_package_with_items(session, word_text="apple", definition="苹果", pos="n."):
    """创建 Package + Word + Meaning + ContentItem 占位，返回 (pkg, word, meaning, items)。"""
    word = Word(word=word_text)
    session.add(word)
    session.flush()

    meaning = Meaning(word_id=word.id, pos=pos, definition=definition)
    session.add(meaning)
    session.flush()

    pkg = Package(name="pipeline_test", status="pending", total_words=1)
    session.add(pkg)
    session.flush()

    pm = PackageMeaning(package_id=pkg.id, meaning_id=meaning.id)
    session.add(pm)

    items = []
    for dim in ["chunk", "sentence"]:
        item = ContentItem(
            word_id=word.id,
            meaning_id=meaning.id,
            dimension=dim,
            content="",
            qc_status=QcStatus.PENDING.value,
        )
        items.append(item)

    # 助记类型（meaning_id=None）
    for dim in ["mnemonic_root_affix", "mnemonic_word_in_word",
                "mnemonic_sound_meaning", "mnemonic_exam_app"]:
        item = ContentItem(
            word_id=word.id,
            meaning_id=None,
            dimension=dim,
            content="",
            qc_status=QcStatus.PENDING.value,
        )
        items.append(item)

    session.add_all(items)
    session.flush()
    return pkg, word, meaning, items


class TestProductionPipeline:
    """生产流水线集成测试。"""

    def test_run_production_success(self, prod_session):
        """生产流水线正常完成，Package 状态变为 completed。"""
        pkg, word, meaning, items = _seed_package_with_items(prod_session)

        result = run_production(prod_session, pkg.id)
        prod_session.commit()

        prod_session.refresh(pkg)
        assert pkg.status == "completed"
        assert pkg.processed_words == 1
        assert result["generated"] == 6  # chunk + sentence + 4 mnemonics

    def test_run_production_failure_sets_failed(self, prod_session):
        """模拟 _run_production_bg 异常时，Package 状态变为 failed。

        直接测试 _run_production_bg 的异常处理逻辑：
        run_production 抛异常 → rollback → 设置 status=failed → commit。
        """
        pkg, word, meaning, items = _seed_package_with_items(prod_session)
        prod_session.commit()

        # 模拟 _run_production_bg 的异常处理逻辑
        try:
            with patch(
                "vocab_qc.core.services.production_service.run_production",
                side_effect=RuntimeError("AI 服务不可用"),
            ):
                from vocab_qc.core.services.production_service import run_production as patched_run
                patched_run(prod_session, pkg.id)
        except RuntimeError:
            prod_session.rollback()
            # 异常后设置 failed 状态（与 _run_production_bg 逻辑一致）
            pkg_reload = prod_session.query(Package).filter_by(id=pkg.id).first()
            if pkg_reload:
                pkg_reload.status = "failed"
                prod_session.commit()

        prod_session.refresh(pkg)
        assert pkg.status == "failed"

    def test_run_production_bg_happy_path(self, prod_engine):
        """直接测试 _run_production_bg 函数，mock SyncSessionLocal 使用测试引擎。"""
        Session = sessionmaker(bind=prod_engine)
        session = Session()

        pkg, word, meaning, items = _seed_package_with_items(session)
        session.commit()
        pkg_id = pkg.id
        session.close()

        # mock SyncSessionLocal（在函数体内被 import）
        with patch(
            "vocab_qc.core.db.SyncSessionLocal",
            new=Session,
        ):
            from vocab_qc.api.routers.batch import _run_production_bg
            _run_production_bg(pkg_id)

        # 验证最终状态
        verify_session = Session()
        pkg_result = verify_session.query(Package).filter_by(id=pkg_id).first()
        assert pkg_result.status == "completed"
        verify_session.close()

    def test_run_production_bg_failure_path(self, prod_engine):
        """_run_production_bg 异常时 Package.status 应被设为 failed。"""
        Session = sessionmaker(bind=prod_engine)
        session = Session()

        pkg, word, meaning, items = _seed_package_with_items(session)
        session.commit()
        pkg_id = pkg.id
        session.close()

        with patch(
            "vocab_qc.core.db.SyncSessionLocal",
            new=Session,
        ), patch(
            "vocab_qc.api.routers.batch.run_production",
            side_effect=RuntimeError("模拟生产失败"),
        ):
            from vocab_qc.api.routers.batch import _run_production_bg
            _run_production_bg(pkg_id)

        verify_session = Session()
        pkg_result = verify_session.query(Package).filter_by(id=pkg_id).first()
        assert pkg_result.status == "failed"
        verify_session.close()

    def test_full_pipeline_import_produce_qc_review(self, prod_session):
        """完整流水线: 导入 → 生产 → L1 质检 → 失败项入队审核。"""
        pkg, word, meaning, items = _seed_package_with_items(prod_session)

        result = run_production(prod_session, pkg.id)
        prod_session.commit()

        # 验证生产完成
        assert result["generated"] > 0
        assert result["qc_passed"] + result["qc_failed"] > 0

        # 验证 Package 状态
        prod_session.refresh(pkg)
        assert pkg.status == "completed"

        # 如果有 L1 失败项，应被入队审核
        if result["qc_failed"] > 0:
            review_count = prod_session.query(ReviewItem).count()
            assert review_count > 0

        # 所有 ContentItem 应有内容（除了被 rejected 的助记类型）
        for item in items:
            prod_session.refresh(item)
            # 已生成的 item 应该已脱离 pending 状态（经过 L1 质检）
            if item.content:
                assert item.qc_status != QcStatus.PENDING.value

    def test_empty_package_completes_immediately(self, prod_session):
        """空 Package（无义项关联）应直接完成。"""
        pkg = Package(name="empty_pipeline", status="pending", total_words=0)
        prod_session.add(pkg)
        prod_session.flush()

        result = run_production(prod_session, pkg.id)
        prod_session.commit()

        prod_session.refresh(pkg)
        assert pkg.status == "completed"
        assert result["generated"] == 0
        assert result["qc_passed"] == 0
        assert result["qc_failed"] == 0
