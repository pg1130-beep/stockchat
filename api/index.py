import os
import json
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from duckduckgo_search import DDGS
from datetime import datetime
from typing import Annotated
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=False)


# ── State ──────────────────────────────────────────────────────────────────
class ChatState(TypedDict):
    messages: Annotated[list, add_messages]


# ── Tools ──────────────────────────────────────────────────────────────────
@tool
def web_search(query: str) -> str:
    """인터넷에서 최신 뉴스나 정보를 검색합니다."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "검색 결과가 없습니다."
    return "\n\n".join(
        f"[{r['title']}]\n{r['body']}\n출처: {r['href']}" for r in results
    )


@tool
def get_current_date() -> str:
    """현재 날짜와 시간을 반환합니다."""
    return datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분 (%A)")


@tool
def get_price(ticker: str) -> str:
    """주식·ETF·지수·암호화폐의 현재 시세를 조회합니다.
    예: AAPL, TSLA, BTC-USD, ^GSPC, 005930.KS"""
    try:
        t = yf.Ticker(ticker.upper())
        fi = t.fast_info
        price, prev = fi.last_price, fi.previous_close
        change_pct = (price - prev) / prev * 100
        hist = t.history(period="5d")
        return (
            f"[{ticker.upper()}]\n"
            f"현재가: {price:,.2f} {fi.currency}\n"
            f"전일 대비: {price-prev:+,.2f} ({change_pct:+.2f}%)\n"
            f"전일 종가: {prev:,.2f} {fi.currency}\n"
            f"5일 최저/최고: {hist['Low'].min():,.2f} / {hist['High'].max():,.2f} {fi.currency}"
        )
    except Exception as e:
        return f"시세 조회 실패 ({ticker}): {e}"


@tool
def get_multiple_prices(tickers: str) -> str:
    """여러 종목 시세를 한번에 조회합니다. 예: 'AAPL,TSLA,BTC-USD'"""
    results = []
    for ticker in [t.strip() for t in tickers.split(",")]:
        try:
            fi = yf.Ticker(ticker.upper()).fast_info
            pct = (fi.last_price - fi.previous_close) / fi.previous_close * 100
            results.append(f"{ticker.upper()}: {fi.last_price:,.2f} {fi.currency} ({pct:+.2f}%)")
        except Exception:
            results.append(f"{ticker.upper()}: 조회 실패")
    return "\n".join(results)


TOOLS = [web_search, get_current_date, get_price, get_multiple_prices]


# ── Graph ──────────────────────────────────────────────────────────────────
def build_graph():
    model = ChatOpenAI(
        model="openai/gpt-oss-120b:free",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    ).bind_tools(TOOLS)

    def chat_node(state: ChatState):
        return {"messages": [model.invoke(state["messages"])]}

    g = StateGraph(ChatState)
    g.add_node("chat", chat_node)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "chat")
    g.add_conditional_edges("chat", tools_condition)
    g.add_edge("tools", "chat")
    return g.compile()


graph = build_graph()

# 워크플로우 리포트용 — 더 빠른 모델 + 토큰 제한 (Vercel 60초 제한 대응)
report_model = ChatOpenAI(
    model="openai/gpt-oss-20b:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=2800,
)


def get_system_prompt() -> str:
    now = datetime.now()
    return (
        f"현재 날짜와 시간: {now.strftime('%Y년 %m월 %d일 %H시 %M분')}\n"
        "당신은 전문 금융 시장 상담 AI입니다. 주식·ETF·암호화폐·지수 시황을 분석하고 "
        "데이터 기반으로 답변합니다. 종목 시세는 get_price 또는 get_multiple_prices 툴을, "
        "뉴스·이슈는 web_search 툴을 사용하세요. "
        "모든 투자 결정은 사용자 본인의 책임임을 명시하세요."
    )


# ── 분석 워크플로우 엔진 (인라인: Vercel이 형제 모듈을 번들하지 않으므로) ──
# ── 한국 주요 종목명 → 티커 매핑 ───────────────────────────────────────────
KR_NAME_TO_TICKER = {
    "삼성전자": "005930.KS", "sk하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "네이버": "035420.KS", "naver": "035420.KS", "카카오": "035720.KS",
    "lg에너지솔루션": "373220.KS", "엘지에너지솔루션": "373220.KS",
    "현대차": "005380.KS", "현대자동차": "005380.KS", "기아": "000270.KS",
    "posco홀딩스": "005490.KS", "포스코홀딩스": "005490.KS",
    "삼성sdi": "006400.KS", "lg화학": "051910.KS", "엘지화학": "051910.KS",
    "셀트리온": "068270.KS", "삼성바이오로직스": "207940.KS",
    "현대모비스": "012330.KS", "kb금융": "105560.KS", "신한지주": "055550.KS",
    "삼성물산": "028260.KS", "lg전자": "066570.KS", "엘지전자": "066570.KS",
    "한미반도체": "042700.KS", "두산에너빌리티": "034020.KS",
    "에코프로비엠": "247540.KQ", "에코프로": "086520.KQ",
    "삼성전자우": "005935.KS", "kt": "030200.KS", "sk텔레콤": "017670.KS",
    "삼성생명": "032830.KS", "하나금융지주": "086790.KS",
    "지역난방공사": "071320.KS", "한국지역난방공사": "071320.KS",
    "한국전력": "015760.KS", "한전": "015760.KS", "한국가스공사": "036460.KS",
    "kt&g": "033780.KS", "케이티앤지": "033780.KS",
    "카카오뱅크": "323410.KS", "카카오페이": "377300.KS",
    "크래프톤": "259960.KS", "하이브": "352820.KS", "넷마블": "251270.KS",
    "sk이노베이션": "096770.KS", "s-oil": "010950.KS", "에스오일": "010950.KS",
    "삼성전기": "009150.KS", "lg디스플레이": "034220.KS", "엘지디스플레이": "034220.KS",
    "포스코퓨처엠": "003670.KS", "두산로보틱스": "454910.KS",
    "hd현대중공업": "329180.KS", "현대중공업": "329180.KS",
    "기업은행": "024110.KS", "우리금융지주": "316140.KS",
    "삼성화재": "000810.KS", "고려아연": "010130.KS", "한화에어로스페이스": "012450.KS",
    "메리츠금융지주": "138040.KS", "삼성생명우": "032831.KS",
    "알테오젠": "196170.KQ", "리노공업": "058470.KQ", "엔켐": "348370.KQ",
    "hmm": "011200.KS", "포스코인터내셔널": "047050.KS",
}


def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)


def _search_kr_ticker(name: str) -> str | None:
    """네이버 종목 자동완성으로 한글 종목명 → yfinance 티커 검색."""
    import urllib.request, urllib.parse, json as _json
    try:
        url = f"https://ac.stock.naver.com/ac?q={urllib.parse.quote(name)}&target=stock"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            items = _json.load(r).get("items", [])
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
    """종목명 또는 티커를 yfinance 티커로 변환."""
    key = name.strip().lower()
    if key in KR_NAME_TO_TICKER:
        return KR_NAME_TO_TICKER[key]
    # 숫자 6자리면 한국 종목으로 간주 (.KS 기본)
    raw = name.strip().upper().replace(".KS", "").replace(".KQ", "")
    if raw.isdigit() and len(raw) == 6:
        return name.strip().upper() if name.strip().upper().endswith((".KS", ".KQ")) else f"{raw}.KS"
    # 한글 종목명은 네이버 자동완성으로 실시간 검색
    if _has_hangul(name):
        found = _search_kr_ticker(name.strip())
        if found:
            return found
    # 그 외는 입력값을 그대로 티커로 사용 (미국주식 등)
    return name.strip().upper()


def _atr14(hist) -> float:
    """14일 Average True Range 계산."""
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
    """Step 1. 정량 데이터 수집 및 핵심 지표 산출."""
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
    gap20 = (cur - ma20) / ma20 * 100  # 이격도

    # 거래량 변화율: 직전 7~13거래일 평균 대비 최근 거래량
    recent_vol = float(volumes.iloc[-1])
    base_vol = float(volumes.iloc[-13:-1].mean())
    vol_change = (recent_vol - base_vol) / base_vol * 100 if base_vol else 0.0

    # 14일 고점 대비 낙폭
    high14 = float(closes.tail(14).max())
    drawdown14 = (cur - high14) / high14 * 100

    # 지지/저항선 (단순 산출)
    support1 = float(closes.tail(14).min())   # 14일 저점
    resistance1 = high14                       # 14일 고점

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
        "resistance1": round(resistance1, 2),
        "atr14": round(atr14, 2),
        "atr_stop": round(cur - 2.0 * atr14, 2),  # ATR 손절가 (2.0×ATR)
    }


def _score_indicator(value, good, bad, higher_is_better=True):
    """지표값 → +2/0/-2 점수 변환."""
    if higher_is_better:
        if value >= good: return 2
        if value <= bad: return -2
        return 0
    else:
        if value <= good: return 2
        if value >= bad: return -2
        return 0


def detect_market_regime() -> dict:
    """Step 1.5. 시장 전환 감지 — 6가지 지표 → 종합점수(-12~+12) → 시장상태."""
    kospi = yf.Ticker("^KS11").history(period="3mo")
    vix = yf.Ticker("^VIX").history(period="1mo")
    usdkrw = yf.Ticker("KRW=X").history(period="1mo")

    checks = {}
    score = 0

    # ① 추세: KOSPI vs MA20/MA60
    kc = kospi["Close"]
    k_cur = float(kc.iloc[-1])
    k_ma20 = float(kc.tail(20).mean())
    k_ma60 = float(kc.tail(60).mean()) if len(kc) >= 60 else k_ma20
    if k_cur > k_ma20 and k_cur > k_ma60: s1 = 2
    elif k_cur > k_ma20 or k_cur > k_ma60: s1 = 0
    else: s1 = -2
    score += s1
    checks["추세"] = {"score": s1, "detail": f"KOSPI {k_cur:,.0f} / MA20 {k_ma20:,.0f}"}

    # ② 거래량: 5일 평균 vs 20일 평균
    kv = kospi["Volume"]
    v5 = float(kv.tail(5).mean())
    v20 = float(kv.tail(20).mean())
    vchg = (v5 - v20) / v20 * 100 if v20 else 0
    if vchg >= 0: s2 = 2
    elif vchg <= -30: s2 = -2
    else: s2 = 0
    score += s2
    checks["거래량"] = {"score": s2, "detail": f"5일/20일 평균 {vchg:+.1f}%"}

    # ③ 외인 수급 프록시: 환율 5일 누적 변동 (원화 강세 = 외인 유입)
    if len(usdkrw) >= 6:
        fx_now = float(usdkrw["Close"].iloc[-1])
        fx_5ago = float(usdkrw["Close"].iloc[-6])
        # USD/KRW 상승 = 원화 약세 = 외인 이탈
        krw_change = (fx_5ago - fx_now) / fx_5ago * 100  # 원화 강세면 +
    else:
        krw_change = 0
    if krw_change >= 0.5: s3 = 2
    elif krw_change <= -0.5: s3 = -2
    else: s3 = 0
    score += s3
    checks["외인수급"] = {"score": s3, "detail": f"원화 5일 {krw_change:+.2f}% (환율 프록시)"}

    # ④ VIX
    vix_cur = float(vix["Close"].iloc[-1]) if not vix.empty else 20
    if vix_cur < 20: s4 = 2
    elif vix_cur >= 30: s4 = -2
    else: s4 = 0
    score += s4
    checks["VIX"] = {"score": s4, "detail": f"{vix_cur:.1f}"}

    # ⑤ 20일 고점 대비 낙폭
    high20 = float(kc.tail(20).max())
    dd = (k_cur - high20) / high20 * 100
    if dd > -5: s5 = 2
    elif dd <= -10: s5 = -2
    else: s5 = 0
    score += s5
    checks["고점대비낙폭"] = {"score": s5, "detail": f"{dd:.1f}%"}

    # ⑥ 연속 하락일
    down_streak = 0
    for i in range(len(kc) - 1, 0, -1):
        if kc.iloc[i] < kc.iloc[i - 1]:
            down_streak += 1
        else:
            break
    if down_streak < 3: s6 = 2
    elif down_streak >= 5: s6 = -2
    else: s6 = 0
    score += s6
    checks["연속하락일"] = {"score": s6, "detail": f"{down_streak}일"}

    state, risk_limit, atr_buffer, constraint = _classify_regime(score)

    return {
        "score": score,
        "state": state,
        "risk_limit": risk_limit,
        "atr_buffer": atr_buffer,
        "constraint": constraint,
        "checks": checks,
        "kospi": round(k_cur, 2),
        "vix": round(vix_cur, 2),
    }


def _classify_regime(score: int):
    """종합점수 → (시장상태, Risk한도, ATR버퍼, 페르소나 제약)."""
    if score >= 7:
        return ("🟢 강세장", "2.5%", "2.2×ATR", "매수 시그널 허용. 외인 SELL 무시.")
    if score >= 3:
        return ("🟢 상승 추세", "2.0%", "2.0×ATR", "매수 허용. 신규 진입 시 거래량 확인 필수.")
    if score >= -2:
        return ("🟡 경계", "1.5%", "1.8×ATR", "신규 매수(🔴) 발행 금지. 🟢까지만 허용.")
    if score >= -6:
        return ("🟠 전환", "1.0%", "1.5×ATR", "🟢 이상 매수 시그널 금지. 비중 축소 검토.")
    return ("🔴 약세장", "0.0% (매수 금지)", "1.2×ATR", "전 페르소나 🔵(매도)/🟡(관망)만 허용.")


# ── 3가지 페르소나 정의 (Step 3) ────────────────────────────────────────────
PERSONAS = {
    "retail": {
        "name": "일반 개미 (Retail)",
        "guide": (
            "개인 투자자 관점. 단기 수급·뉴스 심리에 민감하고 손실 회피 성향이 강하다. "
            "거래량 급감과 지지선 이탈을 가장 경계한다. 말투는 솔직하고 현실적이며, "
            "막연한 기대보다 손실 가능성을 먼저 본다."
        ),
    },
    "institutional": {
        "name": "기관 투자자 (Institutional)",
        "guide": (
            "국내 기관 관점. 밸류에이션·실적·목표주가 괴리율을 중시하고 분할 매매와 "
            "리스크 관리(손절·포지션 사이징)를 철저히 한다. 말투는 절제되고 데이터 기반이다."
        ),
    },
    "foreign": {
        "name": "외국인 투자자 (Foreign)",
        "guide": (
            "외국인 관점. 환율·글로벌 매크로·반도체 업황 등 거시 흐름과 외인 수급을 본다. "
            "원화 약세와 글로벌 리스크오프 시 매도 우위. 말투는 냉정하고 매크로 중심이다."
        ),
    },
}

# 시그널 범례
SIGNAL_LEGEND = "🔴 적극 매수 / 🟢 비중 확대 / 🟡 중립·관망 / 🔵 매도·비중 축소"


def build_analysis_prompt(name: str, quant: dict, regime: dict, qualitative: str) -> str:
    """Step 4. LLM에게 전달할 종합 분석 지시 프롬프트 생성."""
    today = datetime.now().strftime("%Y-%m-%d")
    cur = quant["currency"]

    personas_txt = "\n".join(
        f"- **{p['name']}**: {p['guide']}" for p in PERSONAS.values()
    )

    return f"""당신은 페르소나 기반 종목 분석 워크플로우를 수행하는 금융 분석 엔진입니다.
아래 **실측 정량지표(yfinance)**, **시장 레짐**, **정성 데이터**를 결합해
3가지 투자자 페르소나의 투자 의견서가 포함된 종합 리포트를 마크다운으로 작성하세요.

분석 종목: **{name}** ({quant['ticker']})
보고서 작성일: {today}

## 1. 실측 정량지표 (절대 수정 금지 — 그대로 인용)
| 지표 | 값 |
|------|----|
| 현재가(종가) | {quant['price']:,} {cur} (yfinance 실측값) |
| MA20 | {quant['ma20']:,} {cur} (이격도 {quant['gap20']:+.2f}%, {'🔴 MA20 아래' if quant['below_ma20'] else '🟢 MA20 위'}) |
| MA60 | {quant['ma60'] and f"{quant['ma60']:,.0f} {cur}" or 'N/A'} |
| MA120 | {quant['ma120'] and f"{quant['ma120']:,.0f} {cur}" or 'N/A'} |
| 거래량 변화율 | {quant['vol_change']:+.1f}% (직전 7~13일 평균 대비, 일봉 종가 기준) |
| 14일 고점 대비 낙폭 | {quant['drawdown14']:+.2f}% |
| 1차 지지선 | {quant['support1']:,} {cur} (14일 저점) |
| 1차 저항선 | {quant['resistance1']:,} {cur} (14일 고점) |
| ATR(14) | {quant['atr14']:,} {cur} |
| ATR 손절가(2.0×ATR) | {quant['atr_stop']:,} {cur} |

## 2. 시장 레짐 (Step 1.5)
- **종합 점수: {regime['score']:+d} → {regime['state']}**
- 단일 거래 Risk 한도: {regime['risk_limit']} / ATR 손절 버퍼: {regime['atr_buffer']}
- KOSPI {regime['kospi']:,} / VIX {regime['vix']}
- **페르소나 판단 제약: {regime['constraint']}**

## 3. 정성 데이터 (뉴스/목표주가)
{qualitative}

## 4. 페르소나 정의
{personas_txt}

시그널 범례: {SIGNAL_LEGEND}

## 작성 규칙 (반드시 준수)
1. **실측값만 사용** — 위 정량지표 표의 숫자를 그대로 인용. 추정치/공방 표현 금지.
2. 리포트 **최상단에 시장 상태(점수)**를 명시한 뒤 페르소나 분석 진행.
3. 거래량 변화율 -50% 이상이면 페르소나 강도 하향. -30% 이상이면 관망세 경고.
4. 주가 방향 vs 뉴스 방향 불일치 시 이유 명시.
5. **지지선 이탈 또는 MA20 하회 시** 신규 매수(🔴/🟢) 발행 제약 — 시장 레짐 제약을 우선 적용.
6. **매수(🔴/🟢) 시그널에는 반드시 손절 기준 테이블 동반** (아래 형식).
7. **낙관 편향 금지** — 부정적 지표를 먼저 서술, "~할 수 있다" 최소화, 매수 시에도 "틀릴 수 있는 시나리오" 명시.
8. 경쟁 구도(특히 중국) 리스크 확인 시 bullish 강도 1단계 하향.

## 출력 구조 (이 순서로)
1. **📊 시장 레짐 요약** (점수·상태·제약)
2. **핵심 정량 요약** (현재가·MA20 이격·거래량·낙폭·지지/저항)
3. **3가지 페르소나 투자 의견서** (각 페르소나: 시그널 + 근거 + 반대 시나리오)
4. **🛡️ 손절 기준 및 포지션 사이징** 테이블:

### 🛡️ 손절 기준 및 포지션 사이징
| 항목 | 수치 | 근거 |
|------|------|------|
| ATR(14일) | {quant['atr14']:,} {cur} | 14일 일봉 변동폭 평균 |
| ① ATR 손절가 | {quant['atr_stop']:,} {cur} | 현재가 - 2.0×ATR |
| ② 지지선 손절가 | (지지선 {quant['support1']:,} - ATR×0.5 계산) | 지지선 아래 버퍼 |
| 채택 손절가 | (①② 중 근거 명확한 값) | |
| 2% 룰 최대수량 (5천만원 기준) | (계산) | 자산 대비 비율 표기 |
| 트레일링 전환 | +5% 수익 시 | ATR 트레일링 |

5. **🛡️ 안전 마진(Margin of Safety) 평가** 테이블 (목표주가 컨센서스 하단 기준, 정성 데이터 활용):

### 🛡️ 안전 마진 평가
| 항목 | 수치 | 산출 근거 |
|------|------|-----------|
| 보수적 적정가치 | (목표주가 하단 기반) | |
| 현재 주가 | {quant['price']:,} {cur} | yfinance 실측 |
| 안전 마진(%) | (계산) | (적정가-현재가)/적정가×100 |
| 판정 | 🟢 매우충분(≥25%)/🟡 보통(10~25%)/🔴 부족(<10%) | |
| 최종 매매 지침 | | 안전마진 기반 행동 |

6. **종합 결론** (1~2문장)

리포트 하단에 "보고서 작성일: {today}"와 "데이터: yfinance 실측 종가 기준"을 명시하세요."""


# ── API Routes ─────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    user_text = data.get("message", "").strip()
    history_raw = data.get("history", [])  # [{role, content}, ...]

    if not user_text:
        return jsonify({"error": "빈 메시지"}), 400

    # 클라이언트 히스토리 → LangChain 메시지 변환
    messages = [SystemMessage(content=get_system_prompt())]
    for m in history_raw:
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "ai":
            messages.append(AIMessage(content=m["content"]))
    messages.append(HumanMessage(content=user_text))

    def generate():
        try:
            # stream_mode="messages" → LLM 토큰 단위로 yield
            for chunk, meta in graph.stream({"messages": messages}, stream_mode="messages"):
                # chat 노드의 AI 토큰만 전송 (툴 메시지·툴콜 인자 제외)
                if meta.get("langgraph_node") == "chat" and getattr(chunk, "content", ""):
                    yield f"data: {json.dumps({'delta': chunk.content})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


MARKET_TICKERS = [
    {"symbol": "^GSPC",    "label": "S&P 500"},
    {"symbol": "^IXIC",    "label": "NASDAQ"},
    {"symbol": "^DJI",     "label": "DOW"},
    {"symbol": "^KS11",    "label": "KOSPI"},
    {"symbol": "BTC-USD",  "label": "Bitcoin"},
    {"symbol": "ETH-USD",  "label": "Ethereum"},
    {"symbol": "GC=F",     "label": "Gold"},
    {"symbol": "DX-Y.NYB", "label": "USD Index"},
]

@app.route("/api/market", methods=["GET"])
def market():
    results = []
    for t in MARKET_TICKERS:
        try:
            fi = yf.Ticker(t["symbol"]).fast_info
            price = fi.last_price
            prev  = fi.previous_close
            pct   = (price - prev) / prev * 100
            results.append({
                "symbol":  t["symbol"],
                "label":   t["label"],
                "price":   round(price, 2),
                "change":  round(pct, 2),
                "currency": fi.currency,
            })
        except Exception:
            results.append({"symbol": t["symbol"], "label": t["label"], "error": True})
    return jsonify(results)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """페르소나 기반 종목 심층 분석 워크플로우.
    Step1(정량) → Step1.5(레짐) → Step2(정성) → Step4(LLM 리포트)를 순차 수행."""
    data = request.json or {}
    name = (data.get("ticker") or "").strip()
    if not name:
        return jsonify({"error": "종목명을 입력하세요."}), 400

    def generate():
        try:
            ticker = resolve_ticker(name)

            # 매핑에 없는 한글 종목명은 yfinance가 인식 못 함 → 친절한 안내
            if _has_hangul(ticker):
                msg = f"'{name}' 종목코드를 찾지 못했습니다. 6자리 종목코드로 입력해주세요 (예: 지역난방공사 → 071320)."
                yield f"data: {json.dumps({'error': msg})}\n\n"
                return

            # 진행 상태 알림 (수집 단계)
            yield f"data: {json.dumps({'status': '정량·레짐·뉴스 데이터 수집 중...'})}\n\n"

            def fetch_news():
                try:
                    with DDGS() as ddgs:
                        news = list(ddgs.text(f"{name} 주가 뉴스 목표주가", max_results=5))
                    return "\n".join(f"- {r['title']}: {r['body']}" for r in news) or "- 수집된 뉴스 없음"
                except Exception:
                    return "- (뉴스 수집 실패 — 정성 분석은 일반론으로 제한)"

            with ThreadPoolExecutor(max_workers=3) as ex:
                f_quant = ex.submit(compute_quant, ticker)
                f_regime = ex.submit(detect_market_regime)
                f_news = ex.submit(fetch_news)
                quant = f_quant.result()
                regime = f_regime.result()
                qualitative = f_news.result()

            if quant.get("error"):
                yield f"data: {json.dumps({'error': quant['error']})}\n\n"
                return

            # 메타 정보 먼저 전송
            yield f"data: {json.dumps({'meta': {'ticker': ticker, 'regime_score': regime['score'], 'regime_state': regime['state'], 'price': quant['price'], 'currency': quant['currency']}})}\n\n"
            yield f"data: {json.dumps({'status': '3페르소나 리포트 작성 중...'})}\n\n"

            # Step 4. LLM 리포트 — 토큰 스트리밍
            prompt = build_analysis_prompt(name, quant, regime, qualitative)
            for chunk in report_model.stream([
                SystemMessage(content="당신은 정량 데이터를 절대 변형하지 않는 보수적 금융 분석 엔진입니다."),
                HumanMessage(content=prompt),
            ]):
                if getattr(chunk, "content", ""):
                    yield f"data: {json.dumps({'delta': chunk.content})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'분석 실패: {e}'})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


# ── 정적 페이지 ─────────────────────────────────────────────────────────────
_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")

@app.route("/")
def index():
    with open(_HTML_PATH, encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


if __name__ == "__main__":
    app.run(debug=True, port=8080)
