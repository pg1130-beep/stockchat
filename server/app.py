"""
StockChat 별도 API 서버 (Render 호스팅).

Vercel 앱(api/index.py)은 기존 기능을 그대로 유지하고,
앞으로의 신규 기능은 이 서버에 추가한다.
상시 구동 서버이므로 Vercel의 60초 제한·콜드스타트·번들 250MB 제약이 없다.
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "https://stockchat-kappa.vercel.app",
    "http://localhost:3000",
    "http://localhost:8080",
]
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)

# ── 환경변수 ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


# ── Supabase 헬퍼 ─────────────────────────────────────────────────────────────
def _sb_headers(extra=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _sb_get(path: str) -> list:
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}", headers=_sb_headers()
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _sb_post(path: str, body: dict | list, prefer: str = "") -> bytes:
    data = json.dumps(body).encode()
    headers = _sb_headers({"Prefer": prefer} if prefer else None)
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}", data=data, method="POST", headers=headers
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def _sb_delete(path: str):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        method="DELETE",
        headers=_sb_headers({"Prefer": "return=minimal"}),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


# ── 종목 데이터 (yfinance) ────────────────────────────────────────────────────
KR_NAME_TO_TICKER = {
    "삼성전자": "005930.KS", "sk하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "네이버": "035420.KS", "naver": "035420.KS", "카카오": "035720.KS",
    "lg에너지솔루션": "373220.KS", "현대차": "005380.KS", "현대자동차": "005380.KS",
    "기아": "000270.KS", "posco홀딩스": "005490.KS", "포스코홀딩스": "005490.KS",
    "삼성sdi": "006400.KS", "lg화학": "051910.KS", "엘지화학": "051910.KS",
    "셀트리온": "068270.KS", "삼성바이오로직스": "207940.KS",
    "현대모비스": "012330.KS", "kb금융": "105560.KS", "신한지주": "055550.KS",
    "삼성물산": "028260.KS", "lg전자": "066570.KS", "엘지전자": "066570.KS",
    "한미반도체": "042700.KS", "에코프로비엠": "247540.KQ", "에코프로": "086520.KQ",
    "삼성전자우": "005935.KS", "kt": "030200.KS", "sk텔레콤": "017670.KS",
    "삼성생명": "032830.KS", "하나금융지주": "086790.KS",
    "지역난방공사": "071320.KS", "한국지역난방공사": "071320.KS",
    "한국전력": "015760.KS", "한전": "015760.KS", "한국가스공사": "036460.KS",
    "kt&g": "033780.KS", "케이티앤지": "033780.KS",
    "카카오뱅크": "323410.KS", "카카오페이": "377300.KS",
}


def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)


def _search_kr_ticker(name: str) -> str | None:
    try:
        url = f"https://ac.stock.naver.com/ac?q={urllib.parse.quote(name)}&target=stock"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            items = json.load(r).get("items", [])
        for it in items:
            if it.get("nationCode") != "KOR":
                continue
            code = it.get("code", "")
            if not (code.isdigit() and len(code) == 6):
                continue
            suffix = ".KQ" if it.get("typeCode") == "KOSDAQ" else ".KS"
            return f"{code}{suffix}"
    except Exception:
        pass
    return None


def resolve_ticker(name: str) -> str:
    key = name.strip().lower()
    if key in KR_NAME_TO_TICKER:
        return KR_NAME_TO_TICKER[key]
    raw = name.strip().upper().replace(".KS", "").replace(".KQ", "")
    if raw.isdigit() and len(raw) == 6:
        return name.strip().upper() if name.strip().upper().endswith((".KS", ".KQ")) else f"{raw}.KS"
    if _has_hangul(name):
        found = _search_kr_ticker(name.strip())
        if found:
            return found
    return name.strip().upper()


def _atr14(hist) -> float:
    highs = hist["High"].values
    lows = hist["Low"].values
    closes = hist["Close"].values
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < 14:
        return sum(trs) / len(trs) if trs else 0.0
    return sum(trs[-14:]) / 14


def compute_quant(ticker: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    hist = t.history(period="6mo")
    if hist.empty or len(hist) < 20:
        return {"error": f"{ticker} 데이터 부족"}

    closes = hist["Close"]
    volumes = hist["Volume"]
    cur = float(closes.iloc[-1])
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(60).mean()) if len(closes) >= 60 else None
    ma120 = float(closes.tail(120).mean()) if len(closes) >= 120 else None
    gap20 = (cur - ma20) / ma20 * 100
    recent_vol = float(volumes.iloc[-1])
    base_vol = float(volumes.iloc[-13:-1].mean())
    vol_change = (recent_vol - base_vol) / base_vol * 100 if base_vol else 0.0
    high14 = float(closes.tail(14).max())
    drawdown14 = (cur - high14) / high14 * 100
    support1 = float(closes.tail(14).min())
    atr14 = float(_atr14(hist))
    currency = "KRW" if ticker.endswith((".KS", ".KQ")) else "USD"

    return {
        "ticker": ticker,
        "currency": currency,
        "price": round(cur, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2) if ma60 else None,
        "ma120": round(ma120, 2) if ma120 else None,
        "gap20": round(gap20, 2),
        "below_ma20": cur < ma20,
        "vol_change": round(vol_change, 1),
        "drawdown14": round(drawdown14, 2),
        "support1": round(support1, 2),
        "resistance1": round(high14, 2),
        "atr14": round(atr14, 2),
        "atr_stop": round(cur - 2.0 * atr14, 2),
    }


def detect_market_regime() -> dict:
    import yfinance as yf
    kospi = yf.Ticker("^KS11").history(period="3mo")
    vix = yf.Ticker("^VIX").history(period="1mo")
    usdkrw = yf.Ticker("KRW=X").history(period="1mo")

    score = 0
    checks = {}
    kc = kospi["Close"]
    k_cur = float(kc.iloc[-1])
    k_ma20 = float(kc.tail(20).mean())
    k_ma60 = float(kc.tail(60).mean()) if len(kc) >= 60 else k_ma20

    if k_cur > k_ma20 and k_cur > k_ma60:
        s1 = 2
    elif k_cur > k_ma20 or k_cur > k_ma60:
        s1 = 0
    else:
        s1 = -2
    score += s1
    checks["추세"] = {"score": s1, "detail": f"KOSPI {k_cur:,.0f} / MA20 {k_ma20:,.0f}"}

    kv = kospi["Volume"]
    v5 = float(kv.tail(5).mean())
    v20 = float(kv.tail(20).mean())
    vchg = (v5 - v20) / v20 * 100 if v20 else 0
    s2 = 2 if vchg >= 0 else (-2 if vchg <= -30 else 0)
    score += s2
    checks["거래량"] = {"score": s2, "detail": f"5일/20일 평균 {vchg:+.1f}%"}

    if len(usdkrw) >= 6:
        fx_now = float(usdkrw["Close"].iloc[-1])
        fx_5ago = float(usdkrw["Close"].iloc[-6])
        krw_change = (fx_5ago - fx_now) / fx_5ago * 100
    else:
        krw_change = 0
    s3 = 2 if krw_change >= 0.5 else (-2 if krw_change <= -0.5 else 0)
    score += s3
    checks["외인수급"] = {"score": s3, "detail": f"원화 5일 {krw_change:+.2f}%"}

    vix_cur = float(vix["Close"].iloc[-1]) if not vix.empty else 20
    s4 = 2 if vix_cur < 20 else (-2 if vix_cur >= 30 else 0)
    score += s4
    checks["VIX"] = {"score": s4, "detail": f"{vix_cur:.1f}"}

    high20 = float(kc.tail(20).max())
    dd = (k_cur - high20) / high20 * 100
    s5 = 2 if dd > -5 else (-2 if dd <= -10 else 0)
    score += s5
    checks["고점대비낙폭"] = {"score": s5, "detail": f"{dd:.1f}%"}

    down_streak = 0
    for i in range(len(kc) - 1, 0, -1):
        if kc.iloc[i] < kc.iloc[i - 1]:
            down_streak += 1
        else:
            break
    s6 = 2 if down_streak < 3 else (-2 if down_streak >= 5 else 0)
    score += s6
    checks["연속하락일"] = {"score": s6, "detail": f"{down_streak}일"}

    if score >= 7:
        state = "🟢 강세장"
    elif score >= 3:
        state = "🟢 상승 추세"
    elif score >= -2:
        state = "🟡 경계"
    elif score >= -6:
        state = "🟠 전환"
    else:
        state = "🔴 약세장"

    return {
        "score": score,
        "state": state,
        "kospi": round(k_cur, 2),
        "vix": round(vix_cur, 2),
        "checks": checks,
    }


def generate_one_liner(name: str, quant: dict, regime: dict) -> str:
    """OpenRouter로 종목 한줄 AI 코멘트 생성."""
    if not OPENROUTER_API_KEY:
        return "AI 코멘트 생성 불가 (API 키 미설정)"

    cur = quant["currency"]
    prompt = (
        f"종목: {name} ({quant['ticker']}), 현재가: {quant['price']:,} {cur}, "
        f"MA20 이격: {quant['gap20']:+.2f}%, 거래량 변화: {quant['vol_change']:+.1f}%, "
        f"14일 낙폭: {quant['drawdown14']:+.2f}%, ATR14: {quant['atr14']:,} {cur}, "
        f"시장 레짐: {regime['state']} (점수 {regime['score']:+d})\n\n"
        "위 데이터를 바탕으로 이 종목에 대한 투자자 관점 한줄 코멘트를 작성하세요. "
        "30자 이내, 핵심 포인트 하나만, 낙관 편향 없이."
    )
    body = json.dumps({
        "model": "openai/gpt-oss-20b:free",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 80,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.load(r)
    return result["choices"][0]["message"]["content"].strip()


def build_report_for_ticker(name: str, regime: dict) -> dict:
    """종목 하나에 대한 리포트 데이터 생성."""
    ticker = resolve_ticker(name)
    quant = compute_quant(ticker)
    if "error" in quant:
        return {"name": name, "ticker": ticker, "error": quant["error"]}
    try:
        one_liner = generate_one_liner(name, quant, regime)
    except Exception as e:
        one_liner = f"코멘트 생성 실패: {e}"
    return {
        "name": name,
        "ticker": ticker,
        "price": quant["price"],
        "currency": quant["currency"],
        "gap20": quant["gap20"],
        "below_ma20": quant["below_ma20"],
        "vol_change": quant["vol_change"],
        "drawdown14": quant["drawdown14"],
        "atr14": quant["atr14"],
        "atr_stop": quant["atr_stop"],
        "support1": quant["support1"],
        "resistance1": quant["resistance1"],
        "comment": one_liner,
    }


# ── 기본 라우트 ──────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return jsonify({"service": "stockchat-api", "status": "running"})


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/v2/ping")
def ping():
    return jsonify({"pong": True, "message": "Render API 서버 정상 동작"})


# ── 정기 리포트: 구독 관리 ────────────────────────────────────────────────────
@app.route("/api/v2/report/subscribe", methods=["POST"])
def subscribe():
    """이메일 + 관심종목 구독 등록/수정."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return jsonify({"error": "Supabase 미설정"}), 500

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    tickers_raw = data.get("tickers") or []
    send_hour = int(data.get("send_hour", 8))

    if not email or "@" not in email:
        return jsonify({"error": "유효한 이메일을 입력해주세요."}), 400
    if not tickers_raw:
        return jsonify({"error": "관심종목을 1개 이상 입력해주세요."}), 400
    if not (0 <= send_hour <= 23):
        return jsonify({"error": "send_hour는 0~23 사이여야 합니다."}), 400

    # 종목명 → 티커 변환
    tickers = [resolve_ticker(t) for t in tickers_raw]

    row = {
        "email": email,
        "tickers": tickers,
        "send_hour": send_hour,
        "active": True,
        "updated_at": datetime.utcnow().isoformat(),
    }
    _sb_post(
        "subscriptions",
        [row],
        prefer="resolution=merge-duplicates",
    )
    return jsonify({
        "ok": True,
        "email": email,
        "tickers": tickers,
        "send_hour": send_hour,
        "message": f"구독 등록 완료. 매일 {send_hour}시(KST) 리포트를 발송합니다.",
    })


@app.route("/api/v2/report/subscription", methods=["GET"])
def get_subscription():
    """구독 현황 조회."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return jsonify({"error": "Supabase 미설정"}), 500

    email = (request.args.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email 파라미터가 필요합니다."}), 400

    rows = _sb_get(f"subscriptions?email=eq.{urllib.parse.quote(email)}&select=*")
    if not rows:
        return jsonify({"subscribed": False})
    row = rows[0]
    return jsonify({
        "subscribed": True,
        "email": row["email"],
        "tickers": row["tickers"],
        "send_hour": row["send_hour"],
        "active": row["active"],
        "created_at": row["created_at"],
    })


@app.route("/api/v2/report/subscription", methods=["DELETE"])
def cancel_subscription():
    """구독 취소 (active=false로 설정, 데이터 보존)."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return jsonify({"error": "Supabase 미설정"}), 500

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email이 필요합니다."}), 400

    rows = _sb_get(f"subscriptions?email=eq.{urllib.parse.quote(email)}&select=id")
    if not rows:
        return jsonify({"error": "구독 정보를 찾을 수 없습니다."}), 404

    row_id = rows[0]["id"]
    body = json.dumps({"active": False, "updated_at": datetime.utcnow().isoformat()}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/subscriptions?id=eq.{row_id}",
        data=body,
        method="PATCH",
        headers=_sb_headers({"Prefer": "return=minimal"}),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()

    return jsonify({"ok": True, "message": "구독이 취소되었습니다."})


# ── 정기 리포트: 미리보기 ─────────────────────────────────────────────────────
@app.route("/api/v2/report/preview", methods=["POST"])
def report_preview():
    """
    즉시 리포트 생성 (이메일 발송 없이 JSON 반환).
    body: { "tickers": ["삼성전자", "AAPL"], "email": "optional" }
    """
    data = request.get_json(silent=True) or {}
    tickers_raw = data.get("tickers") or []
    if not tickers_raw:
        return jsonify({"error": "tickers가 필요합니다."}), 400

    # 시장 레짐 1회 조회 후 전 종목 공유
    try:
        regime = detect_market_regime()
    except Exception as e:
        return jsonify({"error": f"시장 레짐 조회 실패: {e}"}), 500

    # 종목별 데이터 병렬 수집
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(build_report_for_ticker, t, regime): t for t in tickers_raw}
        stocks = [f.result() for f in futures]

    return jsonify({
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "regime": {
            "state": regime["state"],
            "score": regime["score"],
            "kospi": regime["kospi"],
            "vix": regime["vix"],
        },
        "stocks": stocks,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
