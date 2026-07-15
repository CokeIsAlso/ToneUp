"""ToneUp 애플리케이션 팩토리.

`create_app()`으로 Flask 인스턴스를 생성한다. 설정·로깅·DB 초기화·블루프린트
등록을 한 곳에서 처리해 테스트/운영에서 동일하게 재사용한다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Type

from flask import Flask, jsonify

from . import db
from .config import Config

__all__ = ["create_app"]


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def create_app(config: Optional[Type[Config]] = None) -> Flask:
    """Flask 앱을 생성·구성해 반환한다."""
    cfg = config or Config
    _configure_logging(cfg.LOG_LEVEL)

    app = Flask(
        __name__,
        template_folder=cfg.TEMPLATE_DIR,
        static_folder=cfg.STATIC_DIR,
    )
    app.config.from_object(cfg)

    os.makedirs(cfg.UPLOAD_FOLDER, exist_ok=True)

    # 데이터 계층 경로를 설정값으로 맞추고 초기화
    db.DB_PATH = cfg.DB_PATH
    db.init_db()

    from .auth import auth_bp
    from .routes import bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(bp)

    logger = logging.getLogger("toneup")
    if not app.config["DEBUG"] and app.config["SECRET_KEY"] == "toneup-dev-secret-change-me":
        logger.warning(
            "기본 SECRET_KEY로 실행 중입니다. 배포 시 TONEUP_SECRET_KEY 환경변수를 반드시 설정하세요."
        )

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.errorhandler(413)
    def _too_large(_e):
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return jsonify({"error": f"파일이 너무 큽니다. 최대 {limit_mb}MB까지 업로드할 수 있습니다."}), 413

    logger.info("ToneUp app initialized (db=%s)", cfg.DB_PATH)
    return app
