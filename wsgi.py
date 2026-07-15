"""WSGI 진입점 — gunicorn/waitress 등에서 `wsgi:app`으로 사용한다."""
from toneup import create_app

app = create_app()
