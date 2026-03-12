"""CLI 模块测试: main / qc_commands / review_commands."""

from unittest.mock import patch

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from vocab_qc.cli.main import app
from vocab_qc.core.db import Base
from vocab_qc.core.models import (
    ContentItem,
    Meaning,
    Phonetic,
    QcStatus,
    ReviewItem,
    ReviewReason,
    ReviewStatus,
    Source,
    Word,
)

runner = CliRunner()


@pytest.fixture()
def cli_session():
    """创建独立的 SQLite 内存会话，供 CLI 测试使用."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def _patch_session(cli_session: Session):
    """将 get_sync_session 替换为返回测试会话."""
    with patch("vocab_qc.cli.qc_commands.get_sync_session", return_value=cli_session), patch(
        "vocab_qc.cli.review_commands.get_sync_session", return_value=cli_session
    ):
        yield


def _seed_word_and_content(session: Session, *, dimension: str = "chunk") -> dict:
    """在测试会话中创建一个 Word + Meaning + ContentItem."""
    word = Word(word="hello")
    session.add(word)
    session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/həˈloʊ/", syllables="hel·lo")
    session.add(phonetic)

    meaning = Meaning(word_id=word.id, pos="interj.", definition="你好")
    session.add(meaning)
    session.flush()

    source = Source(meaning_id=meaning.id, source_name="人教版七年级英语上册（衔接小学）")
    session.add(source)

    content = ContentItem(
        word_id=word.id,
        meaning_id=meaning.id,
        dimension=dimension,
        content="say hello to sb.",
        qc_status=QcStatus.PENDING.value,
    )
    session.add(content)
    session.flush()

    return {"word": word, "meaning": meaning, "content": content}


def _seed_review_item(session: Session, content: ContentItem) -> ReviewItem:
    """创建一个待审核的 ReviewItem."""
    review = ReviewItem(
        content_item_id=content.id,
        word_id=content.word_id,
        meaning_id=content.meaning_id,
        dimension=content.dimension,
        reason=ReviewReason.LAYER1_FAILED.value,
        priority=10,
        status=ReviewStatus.PENDING.value,
    )
    session.add(review)
    session.flush()
    return review


# ---- 帮助信息测试 ----


class TestHelp:
    """各子命令 --help 能正常输出."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "词汇质检" in result.output or "vocab" in result.output

    def test_qc_help(self):
        result = runner.invoke(app, ["qc", "--help"])
        assert result.exit_code == 0
        assert "质检" in result.output

    def test_qc_run_help(self):
        result = runner.invoke(app, ["qc", "run", "--help"])
        assert result.exit_code == 0
        assert "--layer" in result.output

    def test_qc_summary_help(self):
        result = runner.invoke(app, ["qc", "summary", "--help"])
        assert result.exit_code == 0

    def test_review_help(self):
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        assert "审核" in result.output

    def test_review_list_help(self):
        result = runner.invoke(app, ["review", "list", "--help"])
        assert result.exit_code == 0
        assert "--dim" in result.output or "--limit" in result.output

    def test_review_approve_help(self):
        result = runner.invoke(app, ["review", "approve", "--help"])
        assert result.exit_code == 0

    def test_review_regenerate_help(self):
        result = runner.invoke(app, ["review", "regenerate", "--help"])
        assert result.exit_code == 0

    def test_review_edit_help(self):
        result = runner.invoke(app, ["review", "edit", "--help"])
        assert result.exit_code == 0


# ---- QC 命令测试 ----


class TestQcRun:
    """vocab qc run 命令."""

    def test_run_layer1_no_items(self, cli_session, _patch_session):
        """没有内容项时应输出"无内容项需要校验"."""
        result = runner.invoke(app, ["qc", "run", "--layer", "1"])
        assert result.exit_code == 0
        assert "无内容项需要校验" in result.output

    def test_run_layer1_with_content(self, cli_session, _patch_session):
        """有内容项时应输出校验完成信息."""
        _seed_word_and_content(cli_session, dimension="chunk")
        cli_session.commit()

        result = runner.invoke(app, ["qc", "run", "--layer", "1"])
        assert result.exit_code == 0
        # 根据规则结果，可能通过或失败，但一定会有完成提示
        assert "Layer 1 校验完成" in result.output or "无内容项需要校验" in result.output

    def test_run_layer1_with_dimension_filter(self, cli_session, _patch_session):
        """维度筛选参数能正常传递."""
        _seed_word_and_content(cli_session, dimension="chunk")
        cli_session.commit()

        result = runner.invoke(app, ["qc", "run", "--layer", "1", "--dim", "sentence"])
        assert result.exit_code == 0
        # sentence 维度没有数据
        assert "无内容项需要校验" in result.output

    def test_run_layer2_not_implemented(self, cli_session, _patch_session):
        """Layer 2 尚未在 CLI 实现."""
        result = runner.invoke(app, ["qc", "run", "--layer", "2"])
        assert result.exit_code == 0
        assert "Layer 2" in result.output


class TestQcSummary:
    """vocab qc summary 命令."""

    def test_summary_empty(self, cli_session, _patch_session):
        """无质检结果时正常输出空表格."""
        result = runner.invoke(app, ["qc", "summary"])
        assert result.exit_code == 0
        assert "质检统计" in result.output


# ---- Review 命令测试 ----


class TestReviewList:
    """vocab review list 命令."""

    def test_list_empty(self, cli_session, _patch_session):
        """无待审核项时输出提示."""
        result = runner.invoke(app, ["review", "list"])
        assert result.exit_code == 0
        assert "无待审核项" in result.output

    def test_list_with_items(self, cli_session, _patch_session):
        """有待审核项时输出表格."""
        data = _seed_word_and_content(cli_session)
        _seed_review_item(cli_session, data["content"])
        cli_session.commit()

        result = runner.invoke(app, ["review", "list"])
        assert result.exit_code == 0
        assert "待审核队列" in result.output
        assert "chunk" in result.output

    def test_list_with_dimension_filter(self, cli_session, _patch_session):
        """维度筛选只返回对应维度."""
        data = _seed_word_and_content(cli_session, dimension="chunk")
        _seed_review_item(cli_session, data["content"])
        cli_session.commit()

        result = runner.invoke(app, ["review", "list", "--dim", "sentence"])
        assert result.exit_code == 0
        assert "无待审核项" in result.output


class TestReviewApprove:
    """vocab review approve 命令."""

    def test_approve_success(self, cli_session, _patch_session):
        """通过审核成功."""
        data = _seed_word_and_content(cli_session)
        review = _seed_review_item(cli_session, data["content"])
        cli_session.commit()
        review_id = review.id  # commit 后 session 会 expire，提前取出

        result = runner.invoke(app, ["review", "approve", str(review_id)])
        assert result.exit_code == 0
        assert f"#{review_id}" in result.output
        assert "已通过" in result.output


class TestReviewRegenerate:
    """vocab review regenerate 命令."""

    def test_regenerate_success(self, cli_session, _patch_session):
        """重新生成成功."""
        from unittest.mock import patch

        data = _seed_word_and_content(cli_session)
        review = _seed_review_item(cli_session, data["content"])
        cli_session.commit()

        def _mock_regen(session, ci):
            ci.content = "mock regenerated content"

        with patch(
            "vocab_qc.core.services.review_service.ReviewService._do_regenerate",
            side_effect=_mock_regen,
        ):
            result = runner.invoke(app, ["review", "regenerate", str(review.id)])

        assert result.exit_code == 0
        assert "重新生成" in result.output


class TestReviewEdit:
    """vocab review edit 命令."""

    def test_edit_success(self, cli_session, _patch_session):
        """人工修改成功."""
        data = _seed_word_and_content(cli_session)
        review = _seed_review_item(cli_session, data["content"])
        cli_session.commit()
        review_id = review.id

        result = runner.invoke(app, ["review", "edit", str(review_id), "new content here"])
        assert result.exit_code == 0
        assert f"#{review_id}" in result.output
        assert "已修改" in result.output

    def test_edit_with_reviewer(self, cli_session, _patch_session):
        """指定审核者."""
        data = _seed_word_and_content(cli_session)
        review = _seed_review_item(cli_session, data["content"])
        cli_session.commit()

        result = runner.invoke(app, ["review", "edit", str(review.id), "updated", "--by", "test_user"])
        assert result.exit_code == 0
        assert "已修改" in result.output
