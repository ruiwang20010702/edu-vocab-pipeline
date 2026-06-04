"""限流键 get_user_or_ip：已认证按 user_id、未认证 fallback IP。

核心价值：同一 NAT 出口 IP 下的多个审核员拿到各自独立的限流配额，
不再共享同一份 IP 配额、高峰期集体撞 429。
"""
from types import SimpleNamespace

from vocab_qc.api.routers.auth import get_user_or_ip
from vocab_qc.core.config import settings
from vocab_qc.core.models.user import User
from vocab_qc.core.services import auth_service


def _fake_request(cookies=None, headers=None, client_host="1.2.3.4"):
    return SimpleNamespace(
        cookies=cookies or {},
        headers=headers or {},
        client=SimpleNamespace(host=client_host),
    )


def _make_user(db, email="rl@example.com"):
    user = User(email=email, name="RL Tester")
    db.add(user)
    db.flush()
    return user


class TestRateLimitKey:
    def test_authenticated_via_cookie_uses_user_id(self, db_session):
        user = _make_user(db_session)
        token = auth_service.create_jwt(user)
        req = _fake_request(cookies={settings.cookie_name: token})
        assert get_user_or_ip(req) == f"user:{user.id}"

    def test_authenticated_via_bearer_uses_user_id(self, db_session):
        user = _make_user(db_session, email="rl2@example.com")
        token = auth_service.create_jwt(user)
        req = _fake_request(headers={"Authorization": f"Bearer {token}"})
        assert get_user_or_ip(req) == f"user:{user.id}"

    def test_no_token_falls_back_to_ip(self):
        req = _fake_request(client_host="9.9.9.9")
        assert get_user_or_ip(req) == "9.9.9.9"

    def test_invalid_token_falls_back_to_ip(self):
        req = _fake_request(cookies={settings.cookie_name: "garbage.token"}, client_host="9.9.9.9")
        assert get_user_or_ip(req) == "9.9.9.9"

    def test_two_users_same_ip_get_distinct_keys(self, db_session):
        """改造核心：同一出口 IP 下两个审核员 → 不同限流键（旧 IP 逻辑下会相同）。"""
        u1 = _make_user(db_session, email="rl-a@example.com")
        u2 = _make_user(db_session, email="rl-b@example.com")
        t1 = auth_service.create_jwt(u1)
        t2 = auth_service.create_jwt(u2)
        k1 = get_user_or_ip(_fake_request(cookies={settings.cookie_name: t1}, client_host="10.0.0.1"))
        k2 = get_user_or_ip(_fake_request(cookies={settings.cookie_name: t2}, client_host="10.0.0.1"))
        assert k1 == f"user:{u1.id}"
        assert k2 == f"user:{u2.id}"
        assert k1 != k2  # 同 IP 不再共享配额
