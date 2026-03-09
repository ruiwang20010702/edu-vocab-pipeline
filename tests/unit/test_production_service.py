"""production_service 单元测试."""

from vocab_qc.core.models import ContentItem, Meaning, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageMeaning
from vocab_qc.core.services.production_service import run_production


class TestRunProduction:
    def test_basic_production(self, db_session):
        """导入数据后 run_production 应生成内容并运行质检。"""
        word = Word(word="apple")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="苹果")
        db_session.add(meaning)
        db_session.flush()

        pkg = Package(name="prod_test", status="pending", total_words=1)
        db_session.add(pkg)
        db_session.flush()

        pm = PackageMeaning(package_id=pkg.id, meaning_id=meaning.id)
        db_session.add(pm)

        # 创建空占位 ContentItem
        chunk = ContentItem(
            word_id=word.id, meaning_id=meaning.id,
            dimension="chunk", content="", qc_status=QcStatus.PENDING.value,
        )
        sentence = ContentItem(
            word_id=word.id, meaning_id=meaning.id,
            dimension="sentence", content="", qc_status=QcStatus.PENDING.value,
        )
        mnem_items = []
        for dim in ["mnemonic_root_affix", "mnemonic_word_in_word", "mnemonic_sound_meaning", "mnemonic_exam_app"]:
            item = ContentItem(
                word_id=word.id, meaning_id=None,
                dimension=dim, content="", qc_status=QcStatus.PENDING.value,
            )
            mnem_items.append(item)
        db_session.add_all([chunk, sentence] + mnem_items)
        db_session.flush()

        result = run_production(db_session, pkg.id)

        assert result["generated"] == 6  # chunk + sentence + 4 mnemonics
        assert result["qc_passed"] + result["qc_failed"] > 0

        # 验证内容已填充
        db_session.refresh(chunk)
        db_session.refresh(sentence)
        assert chunk.content != ""
        assert sentence.content != ""

        # 验证 Package 状态更新
        db_session.refresh(pkg)
        assert pkg.status == "completed"
        assert pkg.processed_words == 1

    def test_empty_package(self, db_session):
        """空 Package 应直接完成。"""
        pkg = Package(name="empty_prod", status="pending", total_words=0)
        db_session.add(pkg)
        db_session.flush()

        result = run_production(db_session, pkg.id)

        assert result["generated"] == 0
        db_session.refresh(pkg)
        assert pkg.status == "completed"

    def test_skips_already_filled_content(self, db_session):
        """已有内容的 ContentItem 不应被重新生成。"""
        word = Word(word="book")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="书")
        db_session.add(meaning)
        db_session.flush()

        pkg = Package(name="skip_test", status="pending", total_words=1)
        db_session.add(pkg)
        db_session.flush()

        pm = PackageMeaning(package_id=pkg.id, meaning_id=meaning.id)
        db_session.add(pm)

        # 已有内容的 chunk
        chunk = ContentItem(
            word_id=word.id, meaning_id=meaning.id,
            dimension="chunk", content="read a book",
            qc_status=QcStatus.PENDING.value,
        )
        # 空的 sentence
        sentence = ContentItem(
            word_id=word.id, meaning_id=meaning.id,
            dimension="sentence", content="",
            qc_status=QcStatus.PENDING.value,
        )
        db_session.add_all([chunk, sentence])
        db_session.flush()

        result = run_production(db_session, pkg.id)

        # chunk 已有内容，只生成了 sentence
        assert result["generated"] == 1

        db_session.refresh(chunk)
        assert chunk.content == "read a book"  # 未被覆盖

    def test_nonexistent_package(self, db_session):
        """不存在的 Package 应报错。"""
        import pytest
        with pytest.raises(ValueError, match="不存在"):
            run_production(db_session, 99999)

    def test_multi_meaning_production(self, db_session):
        """多义词应为每个义项生成 chunk + sentence。"""
        word = Word(word="run")
        db_session.add(word)
        db_session.flush()

        m1 = Meaning(word_id=word.id, pos="v.", definition="跑")
        m2 = Meaning(word_id=word.id, pos="v.", definition="运行")
        db_session.add_all([m1, m2])
        db_session.flush()

        pkg = Package(name="multi_test", status="pending", total_words=1)
        db_session.add(pkg)
        db_session.flush()

        db_session.add_all([
            PackageMeaning(package_id=pkg.id, meaning_id=m1.id),
            PackageMeaning(package_id=pkg.id, meaning_id=m2.id),
        ])

        # 4 个空占位: chunk×2 + sentence×2
        items = [
            ContentItem(word_id=word.id, meaning_id=m1.id, dimension="chunk", content="", qc_status=QcStatus.PENDING.value),
            ContentItem(word_id=word.id, meaning_id=m1.id, dimension="sentence", content="", qc_status=QcStatus.PENDING.value),
            ContentItem(word_id=word.id, meaning_id=m2.id, dimension="chunk", content="", qc_status=QcStatus.PENDING.value),
            ContentItem(word_id=word.id, meaning_id=m2.id, dimension="sentence", content="", qc_status=QcStatus.PENDING.value),
        ]
        db_session.add_all(items)
        db_session.flush()

        result = run_production(db_session, pkg.id)
        assert result["generated"] == 4

        for item in items:
            db_session.refresh(item)
            assert item.content != ""
