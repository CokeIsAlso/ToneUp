"""인증 (회원가입·로그인·로그아웃) 블루프린트 및 보호 데코레이터.

세션 기반 인증을 사용하며 비밀번호는 werkzeug 해시로 저장한다.
"""
from __future__ import annotations

import logging
import threading
import time
from functools import wraps
from typing import Any, Callable, Optional

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

logger = logging.getLogger("toneup")
auth_bp = Blueprint("auth", __name__)

# ----- 로그인 브루트포스 방지 (IP+이메일별 실패 횟수 제한, 인메모리) -----
_MAX_FAILURES = 5           # 윈도 내 허용 실패 횟수
_FAILURE_WINDOW = 300.0     # 초 (5분)
_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _throttle_key(email: str) -> str:
    return f"{request.remote_addr or '?'}:{email}"


def _is_throttled(email: str) -> bool:
    """실패가 누적된 키인지 확인하고, 오래된 기록은 정리한다."""
    now = time.time()
    key = _throttle_key(email)
    with _failures_lock:
        times = [t for t in _failures.get(key, []) if now - t < _FAILURE_WINDOW]
        if times:
            _failures[key] = times
        else:
            _failures.pop(key, None)
        return len(times) >= _MAX_FAILURES


def _record_failure(email: str) -> None:
    with _failures_lock:
        _failures.setdefault(_throttle_key(email), []).append(time.time())


def _clear_failures(email: str) -> None:
    with _failures_lock:
        _failures.pop(_throttle_key(email), None)


def current_user_id() -> Optional[int]:
    return session.get("user_id")


def login_required(view: Callable) -> Callable:
    """미인증 시 401을 반환한다(데이터/파일 API용). 페이지는 라우트에서 직접 리다이렉트한다."""
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not session.get("user_id"):
            return jsonify({"error": "로그인이 필요합니다."}), 401
        return view(*args, **kwargs)

    return wrapped


def _read_credentials() -> tuple[str, str]:
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    return email, password


def _valid(email: str, password: str) -> bool:
    return bool(email) and "@" in email and len(password) >= 6


@auth_bp.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    return render_template("login.html")


@auth_bp.route("/api/signup", methods=["POST"])
def signup():
    email, password = _read_credentials()
    if not _valid(email, password):
        return jsonify({"error": "올바른 이메일과 6자 이상의 비밀번호가 필요합니다."}), 400
    user_id = db.create_user(email, generate_password_hash(password))
    if user_id is None:
        return jsonify({"error": "이미 가입된 이메일입니다."}), 409
    session.clear()
    session["user_id"] = user_id
    session["email"] = email
    logger.info("signup: user %s", user_id)
    return jsonify({"ok": True, "email": email})


@auth_bp.route("/api/login", methods=["POST"])
def login():
    email, password = _read_credentials()
    if _is_throttled(email):
        return jsonify({"error": "로그인 시도가 너무 많습니다. 5분 후 다시 시도해주세요."}), 429
    user = db.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        _record_failure(email)
        return jsonify({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}), 401
    _clear_failures(email)
    session.clear()
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    return jsonify({"ok": True, "email": user["email"]})


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/api/me")
def me():
    if not session.get("user_id"):
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "email": session.get("email")})
