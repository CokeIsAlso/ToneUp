"""앱 팩토리 + 인증 + 라우트 통합 테스트 (Whisper 불필요)."""

import io

from toneup import create_app
from toneup.config import Config


def _make_app(tmp_path):
    class TestConfig(Config):
        DB_PATH = str(tmp_path / "test.db")
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        SECRET_KEY = "test-secret"

    app = create_app(TestConfig)
    app.testing = True
    return app


def _auth_client(app, email="t@e.com", password="secret123"):
    client = app.test_client()
    client.post("/api/signup", json={"email": email, "password": password})
    return client


def test_index_redirects_when_anonymous(tmp_path):
    client = _make_app(tmp_path).test_client()
    res = client.get("/")
    assert res.status_code in (301, 302)
    assert "/login" in res.headers["Location"]


def test_index_ok_when_logged_in(tmp_path):
    client = _auth_client(_make_app(tmp_path))
    res = client.get("/")
    assert res.status_code == 200
    assert b"ToneUp" in res.data


def test_protected_api_requires_auth(tmp_path):
    client = _make_app(tmp_path).test_client()
    assert client.get("/history").status_code == 401
    assert client.get("/stats").status_code == 401
    assert client.post("/process_audio").status_code == 401


def test_history_empty_when_authed(tmp_path):
    client = _auth_client(_make_app(tmp_path))
    res = client.get("/history")
    assert res.status_code == 200
    assert res.get_json() == []


def test_missing_audio_returns_400(tmp_path):
    client = _auth_client(_make_app(tmp_path))
    res = client.post("/process_audio")
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_stats_empty_when_authed(tmp_path):
    client = _auth_client(_make_app(tmp_path))
    assert client.get("/stats").get_json() == {"sessions": 0}


def test_unknown_record_404(tmp_path):
    client = _auth_client(_make_app(tmp_path))
    assert client.get("/history/999").status_code == 404
    assert client.get("/report/999").status_code == 404


def test_signup_login_flow(tmp_path):
    app = _make_app(tmp_path)
    c1 = app.test_client()
    assert c1.post("/api/signup", json={"email": "a@b.com", "password": "secret1"}).status_code == 200
    # 중복 가입 차단
    assert c1.post("/api/signup", json={"email": "a@b.com", "password": "secret1"}).status_code == 409

    c2 = app.test_client()
    assert c2.post("/api/login", json={"email": "a@b.com", "password": "wrong"}).status_code == 401
    assert c2.post("/api/login", json={"email": "a@b.com", "password": "secret1"}).status_code == 200


def test_signup_validation(tmp_path):
    client = _make_app(tmp_path).test_client()
    assert client.post("/api/signup", json={"email": "bad", "password": "x"}).status_code == 400


def test_history_isolated_between_users(tmp_path):
    app = _make_app(tmp_path)
    a = _auth_client(app, "a@x.com", "passa123")
    b = _auth_client(app, "b@x.com", "passb123")
    # 둘 다 빈 기록이어야 하고 서로 영향 없음
    assert a.get("/history").get_json() == []
    assert b.get("/history").get_json() == []


def test_login_rate_limited_after_repeated_failures(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    email, password = "ratelimit@x.com", "correct123"
    client.post("/api/signup", json={"email": email, "password": password})

    fresh = app.test_client()
    for _ in range(5):
        res = fresh.post("/api/login", json={"email": email, "password": "wrong!!"})
        assert res.status_code == 401
    # 실패 누적 후에는 올바른 비밀번호여도 잠시 차단(429)
    res = fresh.post("/api/login", json={"email": email, "password": password})
    assert res.status_code == 429
    assert "error" in res.get_json()


def test_upload_too_large_returns_json_413(tmp_path):
    class SmallUploadConfig(Config):
        DB_PATH = str(tmp_path / "test.db")
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        SECRET_KEY = "test-secret"
        MAX_CONTENT_LENGTH = 1024  # 1KB로 제한

    app = create_app(SmallUploadConfig)
    app.testing = True
    client = _auth_client(app, "big@x.com", "pass1234")
    res = client.post(
        "/process_audio",
        data={"audio": (io.BytesIO(b"0" * 4096), "big.wav")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 413
    assert "error" in res.get_json()


def test_security_headers_present(tmp_path):
    client = _make_app(tmp_path).test_client()
    res = client.get("/login")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "same-origin"
