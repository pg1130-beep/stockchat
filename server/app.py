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
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "onboarding@resend.dev")
VERCEL_URL = os.getenv("VERCEL_URL", "https://stockchat-kappa.vercel.app")


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

    import requests as _req
    cur = quant["currency"]
    prompt = (
        f"종목: {name} ({quant['ticker']}), 현재가: {quant['price']:,} {cur}, "
        f"MA20 이격: {quant['gap20']:+.2f}%, 거래량 변화: {quant['vol_change']:+.1f}%, "
        f"14일 낙폭: {quant['drawdown14']:+.2f}%, ATR14: {quant['atr14']:,} {cur}, "
        f"시장 레짐: {regime['state']} (점수 {regime['score']:+d})\n\n"
        "위 데이터를 바탕으로 이 종목에 대한 투자자 관점 한줄 코멘트를 작성하세요. "
        "30자 이내, 핵심 포인트 하나만, 낙관 편향 없이."
    )
    resp = _req.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openai/gpt-oss-20b:free",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 80,
        },
        timeout=20,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"].get("content") or ""
    return content.strip() or "데이터 확인 필요"


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


# ── HTML 이메일 템플릿 ────────────────────────────────────────────────────────
def _regime_color(state: str) -> str:
    if "강세" in state or "상승" in state:
        return "#16a34a"
    if "경계" in state:
        return "#ca8a04"
    if "전환" in state:
        return "#ea580c"
    return "#dc2626"


def build_email_html(regime: dict, stocks: list, generated_at: str) -> str:
    date_str = datetime.utcnow().strftime("%Y년 %m월 %d일")
    rc = _regime_color(regime["state"])

    stock_rows = ""
    for s in stocks:
        if "error" in s:
            stock_rows += f"""
            <tr>
              <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;font-weight:600;">{s['name']}</td>
              <td colspan="5" style="padding:12px 8px;border-bottom:1px solid #e5e7eb;color:#ef4444;">
                데이터 조회 실패: {s['error']}
              </td>
            </tr>"""
            continue

        cur = s["currency"]
        fmt = f"{s['price']:,.0f}" if cur == "KRW" else f"{s['price']:,.2f}"
        gap_color = "#16a34a" if s["gap20"] >= 0 else "#dc2626"
        ma_badge = (
            '<span style="background:#fef2f2;color:#dc2626;padding:2px 6px;border-radius:4px;font-size:11px;">MA20 아래</span>'
            if s["below_ma20"]
            else '<span style="background:#f0fdf4;color:#16a34a;padding:2px 6px;border-radius:4px;font-size:11px;">MA20 위</span>'
        )
        stock_rows += f"""
            <tr>
              <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;font-weight:600;">{s['name']}<br>
                <span style="font-size:11px;color:#6b7280;">{s['ticker']}</span>
              </td>
              <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600;">
                {fmt} {cur}
              </td>
              <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;text-align:center;">
                {ma_badge}<br>
                <span style="font-size:12px;color:{gap_color};">이격 {s['gap20']:+.1f}%</span>
              </td>
              <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;text-align:right;font-size:13px;color:#374151;">
                ATR {s['atr14']:,} {cur}<br>
                <span style="color:#6b7280;">손절 {s['atr_stop']:,}</span>
              </td>
              <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;font-size:13px;color:#374151;max-width:200px;">
                {s['comment']}
              </td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockChat 일간 리포트 — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">

  <!-- 헤더 -->
  <tr>
    <td style="background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%);padding:28px 32px;">
      <p style="margin:0;color:rgba(255,255,255,.7);font-size:13px;">{date_str} 장 마감 후 분석</p>
      <h1 style="margin:6px 0 0;color:#ffffff;font-size:24px;font-weight:700;">📈 StockChat 일간 리포트</h1>
    </td>
  </tr>

  <!-- 시장 레짐 -->
  <tr>
    <td style="padding:24px 32px;border-bottom:1px solid #e5e7eb;">
      <h2 style="margin:0 0 12px;font-size:15px;color:#374151;">시장 레짐</h2>
      <table cellpadding="0" cellspacing="0">
        <tr>
          <td style="background:{rc};color:#fff;padding:8px 18px;border-radius:20px;font-weight:700;font-size:15px;">
            {regime['state']}
          </td>
          <td style="padding-left:16px;font-size:14px;color:#6b7280;">
            종합점수 <strong style="color:#111827;">{regime['score']:+d}</strong> &nbsp;|&nbsp;
            KOSPI <strong style="color:#111827;">{regime['kospi']:,}</strong> &nbsp;|&nbsp;
            VIX <strong style="color:#111827;">{regime['vix']}</strong>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- 관심종목 테이블 -->
  <tr>
    <td style="padding:24px 32px;">
      <h2 style="margin:0 0 16px;font-size:15px;color:#374151;">관심종목 분석</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">
        <thead>
          <tr style="background:#f3f4f6;">
            <th style="padding:8px;text-align:left;color:#6b7280;font-weight:600;">종목</th>
            <th style="padding:8px;text-align:right;color:#6b7280;font-weight:600;">현재가</th>
            <th style="padding:8px;text-align:center;color:#6b7280;font-weight:600;">MA20</th>
            <th style="padding:8px;text-align:right;color:#6b7280;font-weight:600;">ATR / 손절가</th>
            <th style="padding:8px;color:#6b7280;font-weight:600;">AI 코멘트</th>
          </tr>
        </thead>
        <tbody>{stock_rows}</tbody>
      </table>
    </td>
  </tr>

  <!-- CTA -->
  <tr>
    <td style="padding:24px 32px;text-align:center;border-top:1px solid #e5e7eb;">
      <a href="{VERCEL_URL}" style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:14px;">
        자세한 분석 보기 →
      </a>
    </td>
  </tr>

  <!-- 푸터 -->
  <tr>
    <td style="padding:20px 32px;background:#f9fafb;text-align:center;">
      <p style="margin:0;font-size:11px;color:#9ca3af;">
        이 리포트는 투자 권유가 아닙니다. 모든 투자 결정은 본인 책임입니다.<br>
        생성 시각: {generated_at} UTC
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def send_email(to: str, subject: str, html: str) -> dict:
    """Resend 공식 SDK로 이메일 발송."""
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY 미설정")
    import resend as _resend
    _resend.api_key = RESEND_API_KEY
    result = _resend.Emails.send({
        "from": RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    })
    if isinstance(result, dict) and result.get("statusCode", 200) >= 400:
        raise RuntimeError(f"Resend 오류: {result}")
    return result if isinstance(result, dict) else {"id": str(result)}


def send_report_to(email: str, tickers_raw: list) -> dict:
    """구독자 1명에게 리포트 생성 + 발송. cron과 수동 트리거 모두 사용."""
    regime = detect_market_regime()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(build_report_for_ticker, t, regime): t for t in tickers_raw}
        stocks = [f.result() for f in futures]

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    date_str = datetime.utcnow().strftime("%Y년 %m월 %d일")
    html = build_email_html(regime, stocks, generated_at)
    subject = f"📈 StockChat 일간 리포트 — {date_str} ({regime['state']})"
    result = send_email(email, subject, html)

    # 발송 로그 기록
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            _sb_post("report_logs", [{
                "email": email,
                "tickers": [s.get("ticker", s.get("name")) for s in stocks],
                "status": "ok",
            }])
        except Exception:
            pass

    return {"email": email, "resend_id": result.get("id"), "stocks": len(stocks)}


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


@app.route("/api/v2/report/check-config")
def check_config():
    """환경변수 설정 확인 (키 값은 노출 안 함)."""
    return jsonify({
        "SUPABASE_URL": bool(SUPABASE_URL),
        "SUPABASE_KEY": bool(SUPABASE_KEY),
        "OPENROUTER_API_KEY": bool(OPENROUTER_API_KEY),
        "RESEND_API_KEY": bool(RESEND_API_KEY),
        "RESEND_API_KEY_prefix": RESEND_API_KEY[:6] if RESEND_API_KEY else None,
        "OPENROUTER_API_KEY_prefix": OPENROUTER_API_KEY[:12] if OPENROUTER_API_KEY else None,
        "RESEND_FROM": RESEND_FROM,
        "VERCEL_URL": VERCEL_URL,
    })


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


# ── 정기 리포트: 발송 ────────────────────────────────────────────────────────
@app.route("/api/v2/report/send-test", methods=["POST"])
def send_test_report():
    """
    테스트 발송 — 구독 여부 관계없이 즉시 이메일 발송.
    body: { "email": "you@example.com", "tickers": ["삼성전자", "AAPL"] }
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    tickers_raw = data.get("tickers") or []
    if not email or "@" not in email:
        return jsonify({"error": "유효한 이메일을 입력해주세요."}), 400
    if not tickers_raw:
        return jsonify({"error": "tickers가 필요합니다."}), 400
    if not RESEND_API_KEY:
        return jsonify({"error": "RESEND_API_KEY가 설정되지 않았습니다."}), 500

    try:
        result = send_report_to(email, tickers_raw)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v2/report/generate-all", methods=["POST"])
def generate_all():
    """
    전체 구독자 일괄 발송 — Render Cron Job이 매일 호출.
    내부 호출 전용: CRON_SECRET 헤더로 인증.
    """
    secret = os.getenv("CRON_SECRET", "")
    if secret and request.headers.get("X-Cron-Secret") != secret:
        return jsonify({"error": "Unauthorized"}), 401

    if not (SUPABASE_URL and SUPABASE_KEY):
        return jsonify({"error": "Supabase 미설정"}), 500

    now_hour_kst = (datetime.utcnow().hour + 9) % 24
    rows = _sb_get(
        f"subscriptions?active=eq.true&send_hour=eq.{now_hour_kst}&select=email,tickers"
    )
    if not rows:
        return jsonify({"ok": True, "sent": 0, "message": "해당 시각 구독자 없음"})

    results = []
    for row in rows:
        try:
            r = send_report_to(row["email"], row["tickers"])
            results.append({"email": row["email"], "status": "ok", "id": r.get("resend_id")})
        except Exception as e:
            results.append({"email": row["email"], "status": "error", "error": str(e)})
            if SUPABASE_URL and SUPABASE_KEY:
                try:
                    _sb_post("report_logs", [{
                        "email": row["email"],
                        "tickers": row["tickers"],
                        "status": "error",
                        "error_msg": str(e),
                    }])
                except Exception:
                    pass

    sent = sum(1 for r in results if r["status"] == "ok")
    return jsonify({"ok": True, "sent": sent, "total": len(rows), "results": results})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
