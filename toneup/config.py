"""애플리케이션 설정.

환경변수를 한 곳에서 읽어 :class:`Config`로 노출한다. `.env` 파일이 있으면
자동으로 로드한다(python-dotenv, 미설치 시 무시).
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # .env 자동 로딩 (선택 의존성)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# 프로젝트 루트 (이 파일: <root>/toneup/config.py)
BASE_DIR: Path = Path(__file__).resolve().parent.parent


class Config:
    """앱 전역 설정값. 환경변수로 모두 덮어쓸 수 있다."""

    # 경로
    BASE_DIR: Path = BASE_DIR
    TEMPLATE_DIR: str = str(BASE_DIR / "templates")
    STATIC_DIR: str = str(BASE_DIR / "static")
    UPLOAD_FOLDER: str = str(BASE_DIR / "uploads")
    DB_PATH: str = os.environ.get("TONEUP_DB", str(BASE_DIR / "toneup.db"))

    # 업로드 제약
    MAX_CONTENT_LENGTH: int = int(os.environ.get("TONEUP_MAX_UPLOAD_MB", "25")) * 1024 * 1024
    ALLOWED_EXT: frozenset[str] = frozenset(
        {"webm", "wav", "ogg", "mp3", "m4a", "flac", "mp4"}
    )

    # 외부 도구 / 정리
    FFMPEG_BIN: str = os.environ.get("FFMPEG_BIN", "ffmpeg")
    FFMPEG_TIMEOUT: int = int(os.environ.get("TONEUP_FFMPEG_TIMEOUT", "120"))
    WAV_TTL_HOURS: float = float(os.environ.get("TONEUP_WAV_TTL_HOURS", "24"))

    # 서버 / 세션
    HOST: str = os.environ.get("HOST", "127.0.0.1")
    PORT: int = int(os.environ.get("PORT", "5000"))
    DEBUG: bool = os.environ.get("FLASK_DEBUG", "0") == "1"
    SECRET_KEY: str = os.environ.get("TONEUP_SECRET_KEY", "toneup-dev-secret-change-me")
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # 로깅
    LOG_LEVEL: str = os.environ.get("TONEUP_LOG_LEVEL", "INFO")
