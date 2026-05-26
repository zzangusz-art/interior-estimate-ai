# -*- coding: utf-8 -*-
"""
인테리어 견적 AI 분석 서비스 - Flask 서버
"""
import os
import uuid
import json
import logging
import threading
from pathlib import Path
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

from utils.file_parser import parse_file
from utils.ai_analyzer import analyze_estimate

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".hwp", ".png", ".jpg", ".jpeg", ".webp"}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _sse(event: str, data: dict) -> str:
    """Server-Sent Events 포맷"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "파일명이 없습니다."}), 400

    if not _allowed(file.filename):
        return jsonify({"error": "지원하지 않는 파일 형식입니다. 지원: PDF, Excel, Word, HWP, PNG, JPG"}), 400

    user_context = request.form.get("context", "")
    ext = Path(file.filename).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / safe_name

    file.save(str(save_path))
    logger.info(f"파일 저장: {safe_name} (원본: {file.filename})")

    def generate():
        try:
            yield _sse("progress", {"step": 1, "message": "파일 읽는 중..."})

            parsed = parse_file(str(save_path), file.filename)
            logger.info(f"파싱 완료: type={parsed['type']}, text_len={len(parsed.get('text',''))}, has_img={bool(parsed.get('image_base64'))}")

            if not parsed.get("text") and not parsed.get("image_base64"):
                yield _sse("error", {"message": "파일에서 내용을 읽을 수 없습니다. 다른 형식으로 변환 후 시도해주세요."})
                return

            yield _sse("progress", {"step": 2, "message": "AI 분석 중... (30~60초 소요)"})

            result = analyze_estimate(parsed, user_context)
            logger.info("AI 분석 완료")

            yield _sse("done", {"result": result})

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            yield _sse("error", {"message": "AI 응답 처리 중 오류가 발생했습니다. 다시 시도해주세요."})
        except Exception as e:
            logger.error(f"분석 오류: {e}", exc_info=True)
            yield _sse("error", {"message": str(e)})
        finally:
            if save_path.exists():
                save_path.unlink()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
