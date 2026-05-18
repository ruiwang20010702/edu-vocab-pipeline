"""POST /api/batches/{id}/produce 的 dimensions 子集 + dry-run preview 集成测试。"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from vocab_qc.api.deps import get_current_user, get_db
from vocab_qc.api.main import app
from vocab_qc.api.routers.auth import limiter
from vocab_qc.core.models import ContentItem, Meaning, QcStatus, Word
from vocab_qc.core.models.package_layer import Package, PackageWord
from vocab_qc.core.models.quality_layer import ReviewItem
from vocab_qc.core.models.user import User

from .conftest import make_db_override, make_test_engine


def _seed_package_with_completed_content(session):
    """1 词 + 2 维度 ContentItem（已 approved）+ 1 review_item，模拟 completed 词包。"""
    word = Word(word="apple")
    session.add(word)
    session.flush()
    meaning = Meaning(word_id=word.id, pos="n.", definition="苹果")
    session.add(meaning)
    session.flush()

    pkg = Package(name="dim_pkg", status="completed", total_words=1)
    session.add(pkg)
    session.flush()
    session.add(PackageWord(package_id=pkg.id, word_id=word.id))

    chunk = ContentItem(
        word_id=word.id, meaning_id=meaning.id, dimension="chunk",
        content="an apple a day", qc_status=QcStatus.APPROVED.value,
    )
    mn = ContentItem(
        word_id=word.id, meaning_id=meaning.id, dimension="mnemonic_sound_meaning",
        content='{"formula":"x"}', qc_status=QcStatus.APPROVED.value,
    )
    session.add_all([chunk, mn])
    session.flush()

    ri = ReviewItem(
        content_item_id=chunk.id, word_id=word.id,
        dimension="chunk", reason="manual_test", status="pending",
    )
    session.add(ri)
    session.commit()
    return pkg.id, chunk.id, mn.id


@pytest.fixture
def batch_app():
    """带 admin 权限 + mock 后台生产 + 关闭 rate limiter 的 TestClient。"""
    engine = make_test_engine()
    session_factory = sessionmaker(bind=engine)
    override_get_db = make_db_override(session_factory)

    admin = User(id=1, email="admin@test.com", name="Admin", role="admin", is_active=True)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin

    # 关掉 slowapi 限速以便同测试内多次触发同 endpoint
    limiter.enabled = False

    # mock 掉后台真实调度（避免触发 AI）
    with patch("vocab_qc.api.routers.batch._run_production_bg_async") as bg_mock:
        client = TestClient(app)
        yield client, session_factory, bg_mock

    app.dependency_overrides.clear()
    limiter.enabled = True
    engine.dispose()


class TestProduceBackwardCompatible:
    """无 body 时维持旧行为（向后兼容）。"""

    def test_produce_without_body(self, batch_app):
        client, sf, bg_mock = batch_app
        s = sf()
        pkg_id, chunk_id, _mn_id = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(f"/api/batches/{pkg_id}/produce")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"batch_id": pkg_id, "status": "processing"}
        bg_mock.assert_called_once()
        # 第二位参数应为 dimensions=None（向后兼容）
        args, _ = bg_mock.call_args
        assert args == (pkg_id, None)

        # 旧调用不应 reset approved ContentItem
        s = sf()
        chunk = s.get(ContentItem, chunk_id)
        assert chunk.qc_status == QcStatus.APPROVED.value
        assert chunk.content == "an apple a day"
        s.close()


class TestProduceWithDimensions:
    """带 body.dimensions 时：先 reset 再触发。"""

    def test_dimensions_reset_then_trigger(self, batch_app):
        client, sf, bg_mock = batch_app
        s = sf()
        pkg_id, chunk_id, mn_id = _seed_package_with_completed_content(s)
        s.close()

        # force_overwrite_recent=True 以禁用 G 方案 prompt 版本判断（seed 时 generated_with_prompt_id=NULL 实际不会被跳，但显式 force 让意图明确）
        resp = client.post(
            f"/api/batches/{pkg_id}/produce",
            json={
                "dimensions": ["chunk", "mnemonic_sound_meaning"],
                "force_overwrite_recent": True,
            },
        )
        assert resp.status_code == 200, resp.text
        bg_mock.assert_called_once()
        args, _ = bg_mock.call_args
        assert args[0] == pkg_id
        assert args[1] == {"chunk", "mnemonic_sound_meaning"}

        # 两个维度都被 reset
        s = sf()
        chunk = s.get(ContentItem, chunk_id)
        mn = s.get(ContentItem, mn_id)
        assert chunk.content == ""
        assert chunk.qc_status == QcStatus.PENDING.value
        assert mn.content == ""
        assert mn.qc_status == QcStatus.PENDING.value
        # 关联 review_item 被级联删
        assert s.query(ReviewItem).filter_by(content_item_id=chunk_id).count() == 0
        s.close()

    def test_invalid_dimension_returns_422(self, batch_app):
        client, sf, _bg_mock = batch_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce",
            json={"dimensions": ["meaning"]},  # meaning 不可重生
        )
        assert resp.status_code == 422
        assert "非法维度" in resp.text

    def test_empty_dimensions_list_returns_422(self, batch_app):
        """dimensions=[] 应明确 422，避免与 None（全量生产）语义混淆。"""
        client, sf, _bg = batch_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce",
            json={"dimensions": []},
        )
        assert resp.status_code == 422

    def test_nonexistent_package_returns_404(self, batch_app):
        client, _sf, _bg = batch_app
        resp = client.post("/api/batches/99999/produce", json={"dimensions": ["chunk"]})
        assert resp.status_code == 404


class TestProducePreview:
    """dry-run preview endpoint。"""

    def test_preview_returns_stats_no_modification(self, batch_app):
        client, sf, _bg = batch_app
        s = sf()
        pkg_id, chunk_id, _mn = _seed_package_with_completed_content(s)
        s.close()

        # force_overwrite_recent=True：禁用 G 方案 prompt 版本判断，让 would_reset 等于 content_items
        resp = client.post(
            f"/api/batches/{pkg_id}/produce/preview",
            json={
                "dimensions": ["chunk", "mnemonic_sound_meaning"],
                "force_overwrite_recent": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_items"] == 2
        assert data["would_reset"] == 2
        assert data["skipped_recently"] == 0
        assert data["review_items"] == 1
        assert data["distinct_words"] == 1
        assert data["by_dimension"] == {"chunk": 1, "mnemonic_sound_meaning": 1}

        # 不改 DB
        s = sf()
        chunk = s.get(ContentItem, chunk_id)
        assert chunk.qc_status == QcStatus.APPROVED.value
        assert chunk.content == "an apple a day"
        assert s.query(ReviewItem).filter_by(content_item_id=chunk_id).count() == 1
        s.close()

    def test_preview_default_does_not_skip_null_prompt_id(self, batch_app):
        """G 方案：默认请求时，generated_with_prompt_id=NULL 的老数据视为未知版本 → 不跳过。

        seed 时 ContentItem 不带 prompt_id（模拟历史数据或未升级 prompt 前）→
        应全部参与重生，would_reset=2，skipped_recently=0。
        """
        client, sf, _bg = batch_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce/preview",
            json={"dimensions": ["chunk", "mnemonic_sound_meaning"]},  # 不传 force
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_items"] == 2
        # G 方案：NULL prompt_id → 视为未知版本 → 不跳过
        assert data["skipped_recently"] == 0
        assert data["would_reset"] == 2

    def test_preview_empty_dimensions_422(self, batch_app):
        client, sf, _bg = batch_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce/preview",
            json={"dimensions": []},
        )
        assert resp.status_code == 422

    def test_preview_invalid_dimension_422(self, batch_app):
        client, sf, _bg = batch_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce/preview",
            json={"dimensions": ["phonetic"]},  # phonetic 不可重生
        )
        assert resp.status_code == 422

    def test_preview_nonexistent_package_404(self, batch_app):
        client, _sf, _bg = batch_app
        resp = client.post(
            "/api/batches/99999/produce/preview",
            json={"dimensions": ["chunk"]},
        )
        assert resp.status_code == 404


class TestReviewerCannotProduceButCanPreview:
    """reviewer 角色：破坏性 produce 被拒，只读 preview 放行（最小权限）。"""

    @pytest.fixture
    def reviewer_app(self):
        engine = make_test_engine()
        session_factory = sessionmaker(bind=engine)
        override_get_db = make_db_override(session_factory)

        reviewer = User(id=2, email="r@test.com", name="R", role="reviewer", is_active=True)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: reviewer
        limiter.enabled = False

        with patch("vocab_qc.api.routers.batch._run_production_bg_async"):
            client = TestClient(app)
            yield client, session_factory

        app.dependency_overrides.clear()
        limiter.enabled = True
        engine.dispose()

    def test_reviewer_produce_with_dimensions_forbidden(self, reviewer_app):
        """reviewer 触发带 dimensions 的破坏性 produce → handler 内 admin 二次校验 403。

        路由 require_role('admin', 'reviewer') 让 reviewer 通过，
        随后 handler 第一行 if body.dimensions and role != 'admin' 拦截。
        精确断言 403（不放宽到 401），若未来路由被误改为 admin-only 此测试仍稳。
        """
        client, sf = reviewer_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce",
            json={"dimensions": ["chunk"]},
        )
        assert resp.status_code == 403
        assert "admin" in resp.text

    def test_reviewer_produce_without_dimensions_succeeds(self, reviewer_app):
        """正向对照：reviewer 不传 dimensions（旧调用路径）应 200，保证向后兼容。

        与 test_reviewer_produce_with_dimensions_forbidden 配对，若 handler 内
        admin 校验被误反转为 == 'admin'，本测试会失败（reviewer 会被无端拒绝）。
        """
        client, sf = reviewer_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(f"/api/batches/{pkg_id}/produce")  # 无 body
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"

    def test_reviewer_can_preview(self, reviewer_app):
        client, sf = reviewer_app
        s = sf()
        pkg_id, _c, _m = _seed_package_with_completed_content(s)
        s.close()

        resp = client.post(
            f"/api/batches/{pkg_id}/produce/preview",
            json={"dimensions": ["chunk"]},
        )
        # preview 是只读 dry-run，reviewer 应可访问
        assert resp.status_code == 200
