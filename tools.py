from datetime import datetime
from langchain_core.tools import tool
from duckduckgo_search import DDGS
import yfinance as yf


@tool
def web_search(query: str) -> str:
    """인터넷에서 최신 뉴스나 정보를 검색합니다."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "검색 결과가 없습니다."
    return "\n\n".join(
        f"[{r['title']}]\n{r['body']}\n출처: {r['href']}"
        for r in results
    )


@tool
def get_current_date() -> str:
    """현재 날짜와 시간을 반환합니다."""
    now = datetime.now()
    return now.strftime("%Y년 %m월 %d일 %H시 %M분 (%A)")


@tool
def get_price(ticker: str) -> str:
    """
    주식·ETF·지수·암호화폐의 현재 시세와 기본 정보를 조회합니다.
    ticker 예시: AAPL, TSLA, SPY, BTC-USD, ETH-USD, ^GSPC(S&P500), ^IXIC(나스닥), 005930.KS(삼성전자)
    """
    try:
        t = yf.Ticker(ticker.upper())
        fi = t.fast_info
        price = fi.last_price
        prev = fi.previous_close
        change = price - prev
        change_pct = change / prev * 100
        currency = fi.currency

        hist = t.history(period="5d")
        week_low = hist["Low"].min()
        week_high = hist["High"].max()

        return (
            f"[{ticker.upper()}]\n"
            f"현재가: {price:,.2f} {currency}\n"
            f"전일 대비: {change:+,.2f} ({change_pct:+.2f}%)\n"
            f"전일 종가: {prev:,.2f} {currency}\n"
            f"5일 최저/최고: {week_low:,.2f} / {week_high:,.2f} {currency}\n"
            f"거래량: {int(fi.three_month_average_volume):,} (3개월 평균)"
        )
    except Exception as e:
        return f"시세 조회 실패 ({ticker}): {e}"


@tool
def get_multiple_prices(tickers: str) -> str:
    """
    여러 종목의 시세를 한번에 조회합니다.
    tickers: 쉼표로 구분된 티커 목록. 예: "AAPL,TSLA,BTC-USD"
    """
    results = []
    for ticker in [t.strip() for t in tickers.split(",")]:
        try:
            t = yf.Ticker(ticker.upper())
            fi = t.fast_info
            price = fi.last_price
            prev = fi.previous_close
            change_pct = (price - prev) / prev * 100
            results.append(f"{ticker.upper()}: {price:,.2f} {fi.currency} ({change_pct:+.2f}%)")
        except Exception:
            results.append(f"{ticker.upper()}: 조회 실패")
    return "\n".join(results)


def get_system_prompt() -> str:
    now = datetime.now()
    return f"""당신은 전문 금융 시장 상담 AI입니다. 오늘은 {now.strftime('%Y년 %m월 %d일 %H시 %M분')}입니다.

역할:
- 주식, ETF, 암호화폐, 지수 등 금융 자산의 현재 시황을 분석하고 설명합니다.
- 사용자의 투자 관련 질문에 데이터 기반으로 답변합니다.
- 최신 뉴스와 시세를 종합해 시장 흐름을 파악합니다.

툴 사용 원칙:
- 종목 시세 → get_price 또는 get_multiple_prices 사용
- 뉴스·이슈·배경 → web_search 사용
- 여러 정보가 필요하면 툴을 순서대로 조합해 종합 분석을 제공합니다.

주의사항:
- 모든 답변은 실제 데이터를 기반으로 합니다.
- 투자 결정은 사용자 본인의 책임임을 항상 명시하세요.
- 확실하지 않은 정보는 추측이라고 명시하세요."""


TOOLS = [web_search, get_current_date, get_price, get_multiple_prices]
