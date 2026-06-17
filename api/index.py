import os
from flask import Flask, request, jsonify
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


def get_system_prompt() -> str:
    now = datetime.now()
    return (
        f"현재 날짜와 시간: {now.strftime('%Y년 %m월 %d일 %H시 %M분')}\n"
        "당신은 전문 금융 시장 상담 AI입니다. 주식·ETF·암호화폐·지수 시황을 분석하고 "
        "데이터 기반으로 답변합니다. 종목 시세는 get_price 또는 get_multiple_prices 툴을, "
        "뉴스·이슈는 web_search 툴을 사용하세요. "
        "모든 투자 결정은 사용자 본인의 책임임을 명시하세요."
    )


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

    try:
        result = graph.invoke({"messages": messages})
        return jsonify({"reply": result["messages"][-1].content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})
