"""개발용 실행 진입점.

    python app.py            # 운영 모드(waitress) 또는 FLASK_DEBUG=1 시 개발 서버
운영 배포는 `wsgi:app` (gunicorn/waitress)을 권장한다.
"""
from toneup import create_app
from toneup.config import Config

app = create_app()

if __name__ == "__main__":
    if Config.DEBUG:
        app.run(host=Config.HOST, port=Config.PORT, debug=True)
    else:
        try:
            from waitress import serve

            print(f" * ToneUp running on http://{Config.HOST}:{Config.PORT} (waitress)")
            serve(app, host=Config.HOST, port=Config.PORT, threads=4)
        except ImportError:
            print(" * waitress 미설치 — 개발 서버로 실행합니다. (pip install waitress 권장)")
            app.run(host=Config.HOST, port=Config.PORT)
