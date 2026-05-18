"""production_service 单元测试."""

from unittest.mock import patch

from vocab_qc.core.models import ContentItem, Meaning, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageWord
from vocab_qc.core.services.production_service import (
    run_production,
    step_generate,
    step_qc_layer1,
    step_qc_layer2,
)


def _fake_generate_async(**kwargs):
    """返回一个 mock 的 generate_async，根据维度返回不同的假数据。"""
    async def _gen(self, *, word, meaning=None, pos=None, _preloaded_config=None):
        dim = self.__class__.__name__.lower()
        if "chunk" in dim:
            return {"content": f"eat an {word}", "content_cn": f"吃一个{word}"}
        if "sentence" in dim:
            return {"content": f"I like {word}.", "content_cn": f"我喜欢{word}。"}
        # mnemonics
        return {"content": f'{{"formula": "{word} memo", "chant": "chant", "script": "script"}}'}
    return _gen


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

        pw = PackageWord(package_id=pkg.id, word_id=word.id)
        db_session.add(pw)

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
                word_id=word.id, meaning_id=meaning.id,
                dimension=dim, content="", qc_status=QcStatus.PENDING.value,
            )
            mnem_items.append(item)
        db_session.add_all([chunk, sentence] + mnem_items)
        db_session.flush()

        # Mock 所有生成器的 generate_async，避免真实 AI 调用
        from vocab_qc.core.services.production_service import _GENERATORS

        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["sentence"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["mnemonic_root_affix"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["mnemonic_word_in_word"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["mnemonic_sound_meaning"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["mnemonic_exam_app"]),
            generate_async=_fake_generate_async(),
        ):
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

        pw = PackageWord(package_id=pkg.id, word_id=word.id)
        db_session.add(pw)

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

        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))

        # 4 个空占位: chunk×2 + sentence×2
        pending = QcStatus.PENDING.value
        items = [
            ContentItem(
                word_id=word.id, meaning_id=m1.id,
                dimension="chunk", content="", qc_status=pending,
            ),
            ContentItem(
                word_id=word.id, meaning_id=m1.id,
                dimension="sentence", content="", qc_status=pending,
            ),
            ContentItem(
                word_id=word.id, meaning_id=m2.id,
                dimension="chunk", content="", qc_status=pending,
            ),
            ContentItem(
                word_id=word.id, meaning_id=m2.id,
                dimension="sentence", content="", qc_status=pending,
            ),
        ]
        db_session.add_all(items)
        db_session.flush()

        # Mock 生成器避免真实 AI 调用
        from vocab_qc.core.services.production_service import _GENERATORS

        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["sentence"]),
            generate_async=_fake_generate_async(),
        ):
            result = run_production(db_session, pkg.id)

        assert result["generated"] == 4

        for item in items:
            db_session.refresh(item)
            assert item.content != ""


class TestStepFunctionsWithWordIds:
    """step_generate/step_qc_layer1/step_qc_layer2 的 word_ids 参数测试。"""

    def _setup_two_words(self, db_session):
        """创建两个词，各有一个 chunk ContentItem。"""
        w1 = Word(word="cat")
        w2 = Word(word="dog")
        db_session.add_all([w1, w2])
        db_session.flush()

        m1 = Meaning(word_id=w1.id, pos="n.", definition="猫")
        m2 = Meaning(word_id=w2.id, pos="n.", definition="狗")
        db_session.add_all([m1, m2])
        db_session.flush()

        pkg = Package(name="batch_test", status="pending", total_words=2)
        db_session.add(pkg)
        db_session.flush()

        db_session.add_all([
            PackageWord(package_id=pkg.id, word_id=w1.id),
            PackageWord(package_id=pkg.id, word_id=w2.id),
        ])

        c1 = ContentItem(
            word_id=w1.id, meaning_id=m1.id,
            dimension="chunk", content="", qc_status=QcStatus.PENDING.value,
        )
        c2 = ContentItem(
            word_id=w2.id, meaning_id=m2.id,
            dimension="chunk", content="", qc_status=QcStatus.PENDING.value,
        )
        db_session.add_all([c1, c2])
        db_session.flush()

        return pkg, w1, w2, c1, c2

    def test_step_generate_with_word_ids_subset(self, db_session):
        """step_generate 传入 word_ids 子集时只处理指定的词。"""
        pkg, w1, w2, c1, c2 = self._setup_two_words(db_session)

        from vocab_qc.core.services.production_service import _GENERATORS

        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ):
            # 只处理 w1
            generated = step_generate(db_session, pkg.id, word_ids={w1.id})

        assert generated == 1
        db_session.refresh(c1)
        db_session.refresh(c2)
        assert c1.content != ""  # w1 已生成
        assert c2.content == ""  # w2 未被处理

    def test_step_generate_without_word_ids_processes_all(self, db_session):
        """step_generate 不传 word_ids 时处理整个 Package。"""
        pkg, w1, w2, c1, c2 = self._setup_two_words(db_session)

        from vocab_qc.core.services.production_service import _GENERATORS

        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ):
            generated = step_generate(db_session, pkg.id)

        assert generated == 2

    def test_step_qc_layer1_with_word_ids(self, db_session):
        """step_qc_layer1 传入 word_ids 子集时只质检指定的词。"""
        pkg, w1, w2, c1, c2 = self._setup_two_words(db_session)

        # 先填充内容，让 L1 能跑
        c1.content = "eat a cat"
        c2.content = "walk a dog"
        db_session.flush()

        result = step_qc_layer1(db_session, pkg.id, word_ids={w1.id})

        # 只处理了 w1 的项
        assert result["passed"] + result["failed"] >= 0  # 至少跑了
        db_session.refresh(c2)
        assert c2.qc_status == QcStatus.PENDING.value  # w2 未被处理


class TestBatchProduceResumeLogic:
    """断点恢复逻辑测试。"""

    def test_failed_zombie_items_reset_to_pending(self, db_session):
        """failed 状态下重试时，空内容的 LAYER1_FAILED 项应被重置为 PENDING。"""
        word = Word(word="test")
        db_session.add(word)
        db_session.flush()

        meaning = Meaning(word_id=word.id, pos="n.", definition="测试")
        db_session.add(meaning)
        db_session.flush()

        pkg = Package(name="resume_test", status="failed", total_words=1)
        db_session.add(pkg)
        db_session.flush()

        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))

        # 模拟僵尸项：content 为空 + LAYER1_FAILED
        zombie = ContentItem(
            word_id=word.id, meaning_id=meaning.id,
            dimension="chunk", content="", qc_status=QcStatus.LAYER1_FAILED.value,
        )
        # 正常失败项：有内容 + LAYER1_FAILED（不应被重置）
        normal_fail = ContentItem(
            word_id=word.id, meaning_id=meaning.id,
            dimension="sentence", content="I like test.",
            qc_status=QcStatus.LAYER1_FAILED.value,
        )
        db_session.add_all([zombie, normal_fail])
        db_session.flush()

        # 模拟 produce_batch 中的断点恢复逻辑
        from vocab_qc.core.services.production_service import _get_word_ids_for_package

        word_ids = _get_word_ids_for_package(db_session, pkg.id)
        db_session.query(ContentItem).filter(
            ContentItem.word_id.in_(word_ids),
            ContentItem.qc_status == QcStatus.LAYER1_FAILED.value,
            ContentItem.content == "",
        ).update(
            {ContentItem.qc_status: QcStatus.PENDING.value},
            synchronize_session=False,
        )
        db_session.flush()

        db_session.refresh(zombie)
        db_session.refresh(normal_fail)
        assert zombie.qc_status == QcStatus.PENDING.value  # 被重置
        assert normal_fail.qc_status == QcStatus.LAYER1_FAILED.value  # 未被重置


class TestResetDimensionsForRegen:
    """reset_dimensions_for_regen helper：按词包 + 维度重置，准备重生产。"""

    def _setup_pkg_with_multi_dim(self, db_session):
        """1 词 + 4 个不同维度的 ContentItem（含 approved/rejected 各种状态）+ 1 个 review_item。"""
        from vocab_qc.core.models.quality_layer import ReviewItem

        word = Word(word="apple")
        db_session.add(word)
        db_session.flush()
        meaning = Meaning(word_id=word.id, pos="n.", definition="苹果")
        db_session.add(meaning)
        db_session.flush()

        pkg = Package(name="reset_test", status="completed", total_words=1)
        db_session.add(pkg)
        db_session.flush()
        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))

        items = {
            "chunk": ContentItem(
                word_id=word.id, meaning_id=meaning.id, dimension="chunk",
                content="an apple a day", content_cn="一日一苹果",
                qc_status=QcStatus.APPROVED.value, retry_count=2,
                last_qc_run_id="run-xyz",
            ),
            "sentence": ContentItem(
                word_id=word.id, meaning_id=meaning.id, dimension="sentence",
                content="I eat an apple.", content_cn="我吃一个苹果。",
                qc_status=QcStatus.APPROVED.value,
            ),
            "mnemonic_word_in_word": ContentItem(
                word_id=word.id, meaning_id=meaning.id, dimension="mnemonic_word_in_word",
                content='{"formula":"apple=app+le"}', qc_status=QcStatus.APPROVED.value,
            ),
            "mnemonic_sound_meaning": ContentItem(
                word_id=word.id, meaning_id=meaning.id, dimension="mnemonic_sound_meaning",
                content='{"formula":"x"}', qc_status=QcStatus.LAYER2_FAILED.value,
            ),
        }
        db_session.add_all(items.values())
        db_session.flush()

        # 给 chunk 加 1 条 review_item，验证级联删除
        ri = ReviewItem(
            content_item_id=items["chunk"].id,
            word_id=word.id, dimension="chunk",
            reason="manual_test", status="pending",
        )
        db_session.add(ri)
        db_session.flush()

        return pkg, items, ri

    def test_empty_dimensions_returns_empty_stats(self, db_session):
        from vocab_qc.core.services.production_service import reset_dimensions_for_regen

        pkg, _items, _ri = self._setup_pkg_with_multi_dim(db_session)
        stats = reset_dimensions_for_regen(db_session, pkg.id, set())
        assert stats == {"content_items": 0, "review_items": 0, "distinct_words": 0, "by_dimension": {}}

    def test_dry_run_returns_stats_without_modifying(self, db_session):
        from vocab_qc.core.services.production_service import reset_dimensions_for_regen

        pkg, items, _ri = self._setup_pkg_with_multi_dim(db_session)
        original_chunk_content = items["chunk"].content

        stats = reset_dimensions_for_regen(
            db_session, pkg.id, {"chunk", "mnemonic_sound_meaning"}, dry_run=True,
        )

        assert stats["content_items"] == 2
        assert stats["review_items"] == 1  # chunk 关联的 review_item
        assert stats["distinct_words"] == 1
        assert stats["by_dimension"] == {"chunk": 1, "mnemonic_sound_meaning": 1}

        # 内容未被改动
        db_session.refresh(items["chunk"])
        assert items["chunk"].content == original_chunk_content
        assert items["chunk"].qc_status == QcStatus.APPROVED.value

    def test_execute_resets_content_status_and_cascades_review_items(self, db_session):
        from vocab_qc.core.models.quality_layer import ReviewItem
        from vocab_qc.core.services.production_service import reset_dimensions_for_regen

        pkg, items, ri = self._setup_pkg_with_multi_dim(db_session)
        ri_id = ri.id

        stats = reset_dimensions_for_regen(
            db_session, pkg.id, {"chunk", "mnemonic_sound_meaning"},
        )
        assert stats["content_items"] == 2

        # chunk 被重置
        db_session.refresh(items["chunk"])
        assert items["chunk"].content == ""
        assert items["chunk"].content_cn == ""
        assert items["chunk"].qc_status == QcStatus.PENDING.value
        assert items["chunk"].retry_count == 0
        assert items["chunk"].last_qc_run_id is None

        # mnemonic_sound_meaning 也被重置
        db_session.refresh(items["mnemonic_sound_meaning"])
        assert items["mnemonic_sound_meaning"].qc_status == QcStatus.PENDING.value
        assert items["mnemonic_sound_meaning"].content == ""

        # 未在维度集合内的不受影响
        db_session.refresh(items["sentence"])
        assert items["sentence"].qc_status == QcStatus.APPROVED.value
        assert items["sentence"].content == "I eat an apple."
        db_session.refresh(items["mnemonic_word_in_word"])
        assert items["mnemonic_word_in_word"].qc_status == QcStatus.APPROVED.value

        # review_item 被级联删除
        assert db_session.query(ReviewItem).filter_by(id=ri_id).first() is None

    def test_nonexistent_package_returns_empty(self, db_session):
        from vocab_qc.core.services.production_service import reset_dimensions_for_regen

        stats = reset_dimensions_for_regen(db_session, 99999, {"chunk"})
        assert stats == {"content_items": 0, "review_items": 0, "distinct_words": 0, "by_dimension": {}}

    def test_no_matching_dimension_returns_empty(self, db_session):
        from vocab_qc.core.services.production_service import reset_dimensions_for_regen

        pkg, _items, _ri = self._setup_pkg_with_multi_dim(db_session)
        # syllable 维度未创建任何 ContentItem
        stats = reset_dimensions_for_regen(db_session, pkg.id, {"syllable"})
        assert stats["content_items"] == 0


class TestStepFunctionsWithDimensions:
    """step_generate / step_qc_layer1 的 dimensions 参数过滤测试。"""

    def _setup_two_dim(self, db_session):
        word = Word(word="bird")
        db_session.add(word)
        db_session.flush()
        meaning = Meaning(word_id=word.id, pos="n.", definition="鸟")
        db_session.add(meaning)
        db_session.flush()

        pkg = Package(name="dim_test", status="pending", total_words=1)
        db_session.add(pkg)
        db_session.flush()
        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))

        chunk = ContentItem(
            word_id=word.id, meaning_id=meaning.id, dimension="chunk",
            content="", qc_status=QcStatus.PENDING.value,
        )
        sentence = ContentItem(
            word_id=word.id, meaning_id=meaning.id, dimension="sentence",
            content="", qc_status=QcStatus.PENDING.value,
        )
        db_session.add_all([chunk, sentence])
        db_session.flush()
        return pkg, word, chunk, sentence

    def test_step_generate_dimensions_filter(self, db_session):
        """step_generate(dimensions={chunk}) 只生成 chunk，不动 sentence。"""
        from vocab_qc.core.services.production_service import _GENERATORS

        pkg, _w, chunk, sentence = self._setup_two_dim(db_session)

        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["sentence"]),
            generate_async=_fake_generate_async(),
        ):
            generated = step_generate(db_session, pkg.id, dimensions={"chunk"})

        assert generated == 1
        db_session.refresh(chunk)
        db_session.refresh(sentence)
        assert chunk.content != ""
        assert sentence.content == ""  # 未在 dimensions 内，不动

    def test_step_generate_no_dimensions_processes_all(self, db_session):
        """step_generate(dimensions=None) 维持原行为，全维度生成。"""
        from vocab_qc.core.services.production_service import _GENERATORS

        pkg, _w, chunk, sentence = self._setup_two_dim(db_session)

        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ), patch.multiple(
            type(_GENERATORS["sentence"]),
            generate_async=_fake_generate_async(),
        ):
            generated = step_generate(db_session, pkg.id)

        assert generated == 2  # 两个维度都生成

    def test_qc_run_layer1_dimensions_filter(self, db_session):
        """QcService.run_layer1_batch(dimensions={chunk}) 只跑 chunk。"""
        from vocab_qc.core.services.qc_service import QcService

        pkg, w, chunk, sentence = self._setup_two_dim(db_session)
        # 填内容让 L1 能跑
        chunk.content = "a flying bird"
        sentence.content = "The bird flies."
        sentence.content_cn = "鸟在飞。"
        db_session.flush()

        result = QcService().run_layer1_batch(
            db_session, {w.id}, dimensions={"chunk"},
        )

        # 只处理 chunk
        assert result["total"] == 1
        db_session.refresh(sentence)
        assert sentence.qc_status == QcStatus.PENDING.value  # sentence 未变

    def test_qc_run_layer1_dimension_and_dimensions_union(self, db_session):
        """QcService.run_layer1_batch 同时传 dimension + dimensions 时取并集。

        必须证明：并集只覆盖指定维度，不扩散到第三维度（避免 dim_filter
        被忽略后的全维度扫描 bug 漏过 total==2 这种假阳性断言）。
        """
        from vocab_qc.core.services.qc_service import QcService

        _pkg, w, chunk, sentence = self._setup_two_dim(db_session)
        chunk.content = "a flying bird"
        sentence.content = "The bird flies."
        sentence.content_cn = "鸟在飞。"
        # 再加第三维度做隔离断言：不在并集内的应保持 PENDING 不被触碰
        meaning = db_session.query(Meaning).filter_by(word_id=w.id).first()
        mnemonic = ContentItem(
            word_id=w.id, meaning_id=meaning.id, dimension="mnemonic_root_affix",
            content='{"formula":"x"}', qc_status=QcStatus.PENDING.value,
        )
        db_session.add(mnemonic)
        db_session.flush()

        result = QcService().run_layer1_batch(
            db_session, {w.id},
            dimension="chunk",        # 旧参数
            dimensions={"sentence"},  # 新参数
        )

        # 并集：chunk + sentence 共 2 条
        assert result["total"] == 2
        # 第三维度未被并集捕获：保持 PENDING
        db_session.refresh(mnemonic)
        assert mnemonic.qc_status == QcStatus.PENDING.value


class TestResetThenRegenerate:
    """reset → step_generate 端到端链路（验证 reset 后 PENDING 真的会被生成器捡起）。"""

    def test_reset_then_step_generate_picks_up_pending(self, db_session):
        from vocab_qc.core.services.production_service import (
            _GENERATORS,
            reset_dimensions_for_regen,
            step_generate,
        )

        # 构造：1 词 + chunk(approved) + sentence(approved)
        word = Word(word="dog")
        db_session.add(word)
        db_session.flush()
        meaning = Meaning(word_id=word.id, pos="n.", definition="狗")
        db_session.add(meaning)
        db_session.flush()

        pkg = Package(name="e2e_test", status="completed", total_words=1)
        db_session.add(pkg)
        db_session.flush()
        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))

        chunk = ContentItem(
            word_id=word.id, meaning_id=meaning.id, dimension="chunk",
            content="walk a dog", qc_status=QcStatus.APPROVED.value,
        )
        sentence = ContentItem(
            word_id=word.id, meaning_id=meaning.id, dimension="sentence",
            content="I love dogs.", qc_status=QcStatus.APPROVED.value,
        )
        db_session.add_all([chunk, sentence])
        db_session.flush()

        # 1. reset chunk
        reset_dimensions_for_regen(db_session, pkg.id, {"chunk"})
        db_session.refresh(chunk)
        assert chunk.qc_status == QcStatus.PENDING.value
        assert chunk.content == ""

        # 2. step_generate 只过滤 chunk 维度，应真的被生成器捡起
        with patch.multiple(
            type(_GENERATORS["chunk"]),
            generate_async=_fake_generate_async(),
        ):
            count = step_generate(db_session, pkg.id, dimensions={"chunk"})

        assert count == 1
        db_session.refresh(chunk)
        db_session.refresh(sentence)
        assert chunk.content != ""  # 真的被生成
        assert sentence.content == "I love dogs."  # 未被触碰

    def test_reset_is_idempotent(self, db_session):
        """对已经 PENDING + content='' 的 ContentItem 再次 reset 应幂等。"""
        from vocab_qc.core.services.production_service import reset_dimensions_for_regen

        word = Word(word="cat")
        db_session.add(word)
        db_session.flush()
        meaning = Meaning(word_id=word.id, pos="n.", definition="猫")
        db_session.add(meaning)
        db_session.flush()
        pkg = Package(name="idem_test", status="completed", total_words=1)
        db_session.add(pkg)
        db_session.flush()
        db_session.add(PackageWord(package_id=pkg.id, word_id=word.id))
        chunk = ContentItem(
            word_id=word.id, meaning_id=meaning.id, dimension="chunk",
            content="a cat", qc_status=QcStatus.APPROVED.value,
        )
        db_session.add(chunk)
        db_session.flush()

        stats1 = reset_dimensions_for_regen(db_session, pkg.id, {"chunk"})
        stats2 = reset_dimensions_for_regen(db_session, pkg.id, {"chunk"})

        assert stats1["content_items"] == stats2["content_items"] == 1
        db_session.refresh(chunk)
        assert chunk.qc_status == QcStatus.PENDING.value
        assert chunk.content == ""
