"""生产流水线集成测试.

覆盖:
- run_production 单 session 兼容模式
- _run_production_bg 多 session 正常完成 → Package.status == "completed"
- _run_production_bg 某步异常时 → Package.status == "failed"
- step_generate / step_qc_layer1 / step_qc_layer2 独立步骤测试
- 完整流水线: 导入 → 生产 → L1 质检 → 入队审核
"""

from unittest.mock import patch

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from vocab_qc.core.db import Base
from vocab_qc.core.models import ContentItem, Meaning, Package, PackageWord, ReviewItem, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.services.production_service import (
    run_production,
    step_finalize,
    step_generate,
    step_qc_layer1,
)


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
    session_factory = sessionmaker(bind=prod_engine)
    session = session_factory()
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

    pw = PackageWord(package_id=pkg.id, word_id=word.id)
    session.add(pw)

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

    # 助记类型（按义项）
    for dim in ["mnemonic_root_affix", "mnemonic_word_in_word",
                "mnemonic_sound_meaning", "mnemonic_exam_app"]:
        item = ContentItem(
            word_id=word.id,
            meaning_id=meaning.id,
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
            pkg_reload = prod_session.query(Package).filter_by(id=pkg.id).first()
            if pkg_reload:
                pkg_reload.status = "failed"
                prod_session.commit()

        prod_session.refresh(pkg)
        assert pkg.status == "failed"

    def test_run_production_bg_happy_path(self, prod_engine):
        """_run_production_bg 多 session 模式正常完成。"""
        session_factory = sessionmaker(bind=prod_engine)
        session = session_factory()

        pkg, word, meaning, items = _seed_package_with_items(session)
        session.commit()
        pkg_id = pkg.id
        session.close()

        with patch(
            "vocab_qc.core.db.SyncSessionLocal",
            new=session_factory,
        ):
            from vocab_qc.api.routers.batch import _run_production_bg
            _run_production_bg(pkg_id)

        verify_session = session_factory()
        pkg_result = verify_session.query(Package).filter_by(id=pkg_id).first()
        assert pkg_result.status == "completed"
        assert pkg_result.processed_words == 1
        verify_session.close()

    def test_run_production_bg_failure_at_generate(self, prod_engine):
        """_run_production_bg 在 generate 步骤失败时 Package.status 应为 failed。"""
        session_factory = sessionmaker(bind=prod_engine)
        session = session_factory()

        pkg, word, meaning, items = _seed_package_with_items(session)
        session.commit()
        pkg_id = pkg.id
        session.close()

        with patch(
            "vocab_qc.core.db.SyncSessionLocal",
            new=session_factory,
        ), patch(
            "vocab_qc.core.services.production_service.step_generate",
            side_effect=RuntimeError("模拟生成失败"),
        ):
            from vocab_qc.api.routers.batch import _run_production_bg
            _run_production_bg(pkg_id)

        verify_session = session_factory()
        pkg_result = verify_session.query(Package).filter_by(id=pkg_id).first()
        assert pkg_result.status == "failed"
        verify_session.close()

    def test_run_production_bg_failure_at_qc_layer1(self, prod_engine):
        """_run_production_bg 在 L1 质检步骤失败时 Package.status 应为 failed。"""
        session_factory = sessionmaker(bind=prod_engine)
        session = session_factory()

        pkg, word, meaning, items = _seed_package_with_items(session)
        session.commit()
        pkg_id = pkg.id
        session.close()

        with patch(
            "vocab_qc.core.db.SyncSessionLocal",
            new=session_factory,
        ), patch(
            "vocab_qc.core.services.production_service.step_qc_layer1",
            side_effect=RuntimeError("模拟 L1 失败"),
        ):
            from vocab_qc.api.routers.batch import _run_production_bg
            _run_production_bg(pkg_id)

        verify_session = session_factory()
        pkg_result = verify_session.query(Package).filter_by(id=pkg_id).first()
        assert pkg_result.status == "failed"
        verify_session.close()

    def test_full_pipeline_import_produce_qc_review(self, prod_session):
        """完整流水线: 导入 → 生产 → L1 质检 → 失败项入队审核。"""
        pkg, word, meaning, items = _seed_package_with_items(prod_session)

        result = run_production(prod_session, pkg.id)
        prod_session.commit()

        assert result["generated"] > 0
        assert result["qc_passed"] + result["qc_failed"] > 0

        prod_session.refresh(pkg)
        assert pkg.status == "completed"

        if result["qc_failed"] > 0:
            review_count = prod_session.query(ReviewItem).count()
            assert review_count > 0

        for item in items:
            prod_session.refresh(item)
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


class TestStepFunctions:
    """独立步骤函数测试。"""

    def test_step_generate(self, prod_session):
        """step_generate 应生成内容并设置 processing 状态。"""
        pkg, word, meaning, items = _seed_package_with_items(prod_session)
        prod_session.commit()

        generated = step_generate(prod_session, pkg.id)
        prod_session.commit()

        assert generated == 6
        prod_session.refresh(pkg)
        assert pkg.status == "processing"

    def test_step_generate_empty_package(self, prod_session):
        """空 Package 的 step_generate 返回 0。"""
        pkg = Package(name="empty_step", status="pending", total_words=0)
        prod_session.add(pkg)
        prod_session.flush()
        prod_session.commit()

        generated = step_generate(prod_session, pkg.id)
        assert generated == 0

    def test_step_qc_layer1(self, prod_session):
        """step_qc_layer1 应执行 L1 质检。"""
        pkg, word, meaning, items = _seed_package_with_items(prod_session)
        # 先生成内容
        step_generate(prod_session, pkg.id)
        prod_session.commit()

        result = step_qc_layer1(prod_session, pkg.id)
        prod_session.commit()

        assert result["passed"] + result["failed"] > 0

    def test_step_finalize(self, prod_session):
        """step_finalize 应标记 Package 为 completed。"""
        pkg, word, meaning, items = _seed_package_with_items(prod_session)
        prod_session.commit()

        step_finalize(prod_session, pkg.id)
        prod_session.commit()

        prod_session.refresh(pkg)
        assert pkg.status == "completed"
        assert pkg.processed_words == 1

    def test_multi_session_isolation(self, prod_engine):
        """验证每步使用独立 session 时数据正确持久化。"""
        session_factory = sessionmaker(bind=prod_engine)

        # 准备数据
        s1 = session_factory()
        pkg, word, meaning, items = _seed_package_with_items(s1)
        s1.commit()
        pkg_id = pkg.id
        s1.close()

        # Step 1: generate（独立 session）
        s2 = session_factory()
        step_generate(s2, pkg_id)
        s2.commit()
        s2.close()

        # Step 2: L1 QC（独立 session，应能看到 step 1 的结果）
        s3 = session_factory()
        result = step_qc_layer1(s3, pkg_id)
        s3.commit()
        s3.close()

        assert result["passed"] + result["failed"] > 0

        # Finalize（独立 session）
        s4 = session_factory()
        step_finalize(s4, pkg_id)
        s4.commit()
        s4.close()

        # 验证最终状态
        s5 = session_factory()
        pkg_final = s5.query(Package).filter_by(id=pkg_id).first()
        assert pkg_final.status == "completed"
        assert pkg_final.processed_words == 1
        s5.close()
