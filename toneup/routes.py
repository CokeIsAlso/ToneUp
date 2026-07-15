"""HTTP 라우트 (Flask Blueprint)."""
from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)

from . import db
from .auth import current_user_id, login_required
from .services.analysis import analyze_audio
from .services.coaching import generate_ai_feedback
from .services.report import build_report_pdf

_VALID_MODES = {"free", "reading", "interview", "presentation"}

logger = logging.getLogger("toneup")
bp = Blueprint("main", __name__)


def _cleanup_old_files() -> None:
    """업로드 폴더에서 TTL을 초과한 파일을 삭제한다."""
    ttl = current_app.config["WAV_TTL_HOURS"]
    folder = current_app.config["UPLOAD_FOLDER"]
    if ttl <= 0:
        return
    cutoff = time.time() - ttl * 3600
    try:
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def _get_ext(filename: str) -> str:
    """허용 확장자를 추출한다. 없거나 미허용이면 webm으로 간주."""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()
        if ext in current_app.config["ALLOWED_EXT"]:
            return ext
    return "webm"


@bp.route("/")
def index():
    if not current_user_id():
        return redirect(url_for("auth.login_page"))
    return render_template("index.html", user_email=session.get("email"))


@bp.route("/uploads/<path:filename>")
@login_required
def download_file(filename: str):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@bp.route("/audio/<path:filename>")
@login_required
def stream_audio(filename: str):
    """녹음 다시 듣기용 인라인 스트리밍(다운로드가 아닌 재생)."""
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.route("/process_audio", methods=["POST"])
@login_required
def process_audio():
    if "audio" not in request.files:
        return jsonify({"error": "오디오 파일이 전송되지 않았습니다."}), 400

    file = request.files["audio"]
    if not file or file.filename == "":
        return jsonify({"error": "빈 파일입니다."}), 400

    _cleanup_old_files()
    folder = current_app.config["UPLOAD_FOLDER"]
    ffmpeg_bin = current_app.config["FFMPEG_BIN"]

    ext = _get_ext(file.filename)
    job_id = uuid.uuid4().hex  # 요청별 고유 ID로 동시 요청 충돌 방지
    orig_path = os.path.join(folder, f"{job_id}_orig.{ext}")
    wav_name = f"{job_id}.wav"
    wav_path = os.path.join(folder, wav_name)

    try:
        file.save(orig_path)

        cmd = [
            ffmpeg_bin, "-nostdin", "-y",
            "-i", orig_path, "-ac", "1", "-ar", "16000", wav_path,
        ]
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=current_app.config["FFMPEG_TIMEOUT"],
            )
        except FileNotFoundError:
            logger.error("ffmpeg not found: %s", ffmpeg_bin)
            return jsonify({
                "error": "ffmpeg를 찾을 수 없습니다. 설치 후 PATH에 등록하거나 FFMPEG_BIN 환경변수를 설정하세요."
            }), 500
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg conversion timed out")
            return jsonify({"error": "오디오 변환 시간이 초과되었습니다. 더 짧은 파일로 시도해보세요."}), 500
        except subprocess.CalledProcessError as e:
            logger.error("ffmpeg conversion failed")
            return jsonify({
                "error": "오디오 변환에 실패했습니다.",
                "detail": e.stderr.decode(errors="ignore")[:1000],
            }), 500

        result = analyze_audio(wav_path)
        if result is None:
            return jsonify({"error": "음성을 인식할 수 없습니다. 더 길고 또렷하게 녹음해보세요."}), 422

        mode = request.form.get("mode", "free")
        if mode not in _VALID_MODES:
            mode = "free"
        context = (request.form.get("context") or "")[:500]
        result["mode"] = mode
        result["wav_file"] = wav_name  # 기록에서 다시 듣기용

        feedback = generate_ai_feedback(result, mode, context)
        result["ai_coaching"] = feedback.get("coaching")
        result["ai_improved"] = feedback.get("improved_text")

        try:
            result["record_id"] = db.save_record(result, current_user_id())
        except Exception as e:
            logger.exception("save_record failed: %s", e)
            result["record_id"] = None

        result["server_file_url"] = f"/uploads/{wav_name}"
        return jsonify(result)
    finally:
        if os.path.exists(orig_path):  # 원본은 분석 후 정리(WAV는 다운로드용 유지)
            try:
                os.remove(orig_path)
            except OSError:
                pass


@bp.route("/history", methods=["GET"])
@login_required
def history():
    return jsonify(db.list_records(current_user_id()))


@bp.route("/stats", methods=["GET"])
@login_required
def stats():
    return jsonify(db.get_stats(current_user_id()))


@bp.route("/history/<int:record_id>", methods=["GET"])
@login_required
def history_detail(record_id: int):
    rec = db.get_record(record_id, current_user_id())
    if rec is None:
        abort(404)
    return jsonify(rec)


@bp.route("/history/<int:record_id>", methods=["DELETE"])
@login_required
def history_delete(record_id: int):
    ok = db.delete_record(record_id, current_user_id())
    return jsonify({"deleted": ok}), (200 if ok else 404)


@bp.route("/report/<int:record_id>", methods=["GET"])
@login_required
def report(record_id: int):
    rec = db.get_record(record_id, current_user_id())
    if rec is None:
        abort(404)
    pdf = build_report_pdf(rec)
    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"toneup_report_{record_id}.pdf",
    )
