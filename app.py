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

# Railway 프록시 idle timeout 방어용 heartbeat 간격 (초)
HEARTBEAT_INTERVAL = 8


def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _sse(event: str, data: dict) -> str:
    """Server-Sent Events 포맷 (개행 없이 단일 data 라인 보장)"""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _heartbeat(step: int, message: str) -> str:
    """연결 유지용 heartbeat SSE"""
    return _sse("progress", {"step": step, "message": message})


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
            # ── Step 1: 파일 파싱 ──────────────────────────────────────
            yield _sse("progress", {"step": 1, "message": "파일 읽는 중..."})

            try:
                parsed = parse_file(str(save_path), file.filename)
            except Exception as e:
                logger.error(f"파싱 오류: {e}", exc_info=True)
                yield _sse("error", {"message": f"파일을 읽을 수 없습니다: {e}"})
                return

            logger.info(
                f"파싱 완료: type={parsed['type']}, "
                f"text_len={len(parsed.get('text', ''))}, "
                f"has_img={bool(parsed.get('image_base64'))}"
            )

            if not parsed.get("text") and not parsed.get("image_base64"):
                yield _sse("error", {"message": "파일에서 내용을 읽을 수 없습니다. 다른 형식으로 변환 후 시도해주세요."})
                return

            # ── Step 2: Claude AI 분석 (별도 스레드 + heartbeat) ─────────
            yield _sse("progress", {"step": 2, "message": "AI 분석 시작 중..."})

            container: dict = {}
            finished = threading.Event()

            def _run_ai():
                try:
                    container["result"] = analyze_estimate(parsed, user_context)
                    logger.info("AI 분석 완료")
                except Exception as exc:
                    logger.error(f"AI 분석 오류: {exc}", exc_info=True)
                    container["error"] = str(exc)
                finally:
                    finished.set()

            ai_thread = threading.Thread(target=_run_ai, daemon=True)
            ai_thread.start()

            # ── Heartbeat 루프: 8초마다 이벤트 전송 → Railway idle timeout 방지
            heartbeat_messages = [
                (2, "견적 항목 파악 중..."),
                (3, "시장가 비교 중..."),
                (3, "과다 청구 항목 검토 중..."),
                (4, "협상 전략 수립 중..."),
                (4, "분석 보고서 작성 중..."),
                (4, "최종 검토 중..."),
            ]
            hb_idx = 0
            while not finished.wait(timeout=HEARTBEAT_INTERVAL):
                step, msg = heartbeat_messages[min(hb_idx, len(heartbeat_messages) - 1)]
                yield _heartbeat(step, msg)
                hb_idx += 1

            # ── 결과 반환 ──────────────────────────────────────────────
            if "error" in container:
                yield _sse("error", {"message": container["error"]})
            else:
                yield _sse("done", {"result": container["result"]})

        except GeneratorExit:
            # 클라이언트가 연결을 끊은 경우 — 조용히 종료
            logger.info("클라이언트 연결 종료 (GeneratorExit)")
        except Exception as e:
            logger.error(f"SSE 제너레이터 오류: {e}", exc_info=True)
            try:
                yield _sse("error", {"message": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."})
            except Exception:
                pass
        finally:
            if save_path.exists():
                try:
                    save_path.unlink()
                except Exception:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",   # nginx/Railway 버퍼링 비활성화
            "Connection": "keep-alive",
        },
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
