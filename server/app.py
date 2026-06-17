"""
StockChat 별도 API 서버 (Render 호스팅).

Vercel 앱(api/index.py)은 기존 기능을 그대로 유지하고,
앞으로의 신규 기능은 이 서버에 추가한다.
상시 구동 서버이므로 Vercel의 60초 제한·콜드스타트·번들 250MB 제약이 없다.
"""
import os
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# 프론트엔드(Vercel) 및 로컬 개발에서의 호출 허용
ALLOWED_ORIGINS = [
    "https://stockchat-kappa.vercel.app",
    "http://localhost:3000",
    "http://localhost:8080",
]
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)


# ── 기본 라우트 ──────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return jsonify({"service": "stockchat-api", "status": "running"})


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


# ── 신규 기능은 아래에 추가하세요 ────────────────────────────────────────────
# 예시 엔드포인트 (정상 배포 확인용)
@app.route("/api/v2/ping")
def ping():
    return jsonify({"pong": True, "message": "Render API 서버 정상 동작"})


if __name__ == "__main__":
    # 로컬 실행: python app.py  → http://localhost:8000
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
