# MarketBot — LangGraph 서비스 구조도

## 1. 전체 시스템 구조

```mermaid
graph TD
    Browser["🖥️ 브라우저\n(index.html)"]

    subgraph Vercel["Vercel Serverless (api/index.py)"]
        ChatAPI["/api/chat\nSSE 스트리밍"]
        AnalyzeAPI["/api/analyze\n심층 분석 워크플로우"]
        MarketAPI["/api/market\n시세 조회"]
        MemoAPI["/api/memo\n메모 저장"]
    end

    subgraph Render["Render Web Service (server/app.py)"]
        SubscribeAPI["/api/v2/report/subscribe\n구독 등록"]
        GenerateAPI["/api/v2/report/generate-all\n일괄 발송"]
        PreviewAPI["/api/v2/report/preview\n미리보기"]
    end

    subgraph External["외부 서비스"]
        OpenRouter["OpenRouter API\ngpt-oss-120b (채팅)\ngpt-oss-20b (리포트)"]
        yfinance["yfinance\n실시간 시세·지표"]
        DuckDuckGo["DuckDuckGo Search\n뉴스 검색"]
        Naver["네이버 자동완성 API\n한글 종목명 → 티커"]
        Supabase["Supabase DB\nmemos / subscriptions\nreport_logs"]
        Resend["Resend\n이메일 발송"]
    end

    GHActions["⏰ GitHub Actions\n매일 08:00 KST"]

    Browser -->|"POST + SSE"| ChatAPI
    Browser -->|"POST + SSE"| AnalyzeAPI
    Browser -->|"GET"| MarketAPI
    Browser -->|"GET/POST"| MemoAPI
    Browser -->|"POST/GET/DELETE"| SubscribeAPI

    ChatAPI --> OpenRouter
    ChatAPI --> yfinance
    ChatAPI --> DuckDuckGo
    AnalyzeAPI --> OpenRouter
    AnalyzeAPI --> yfinance
    AnalyzeAPI --> DuckDuckGo
    AnalyzeAPI --> Naver
    MarketAPI --> yfinance
    MemoAPI --> Supabase

    GHActions -->|"POST X-Cron-Secret"| GenerateAPI
    GenerateAPI --> yfinance
    GenerateAPI --> OpenRouter
    GenerateAPI --> Supabase
    GenerateAPI --> Resend
    SubscribeAPI --> Supabase
```

---

## 2. LangGraph 채팅 그래프 (일반 채팅)

```mermaid
stateDiagram-v2
    [*] --> START
    START --> chat : 사용자 메시지 + 대화 히스토리

    chat --> tools : tool_call 포함된 응답\n(tools_condition = True)
    chat --> END : 일반 텍스트 응답\n(tools_condition = False)

    tools --> chat : 툴 실행 결과 반환

    note right of chat
        모델: gpt-oss-120b (OpenRouter)
        바인딩 툴 4개:
        · web_search
        · get_current_date
        · get_price
        · get_multiple_prices
    end note

    note right of tools
        LangGraph ToolNode
        (자동 디스패치)
    end note
```

### 채팅 SSE 스트리밍 흐름

```mermaid
sequenceDiagram
    participant B as 브라우저
    participant V as Vercel /api/chat
    participant G as LangGraph Graph
    participant OR as OpenRouter
    participant T as Tool (yfinance/DDG)

    B->>V: POST {message, history}
    V->>G: graph.stream(messages, stream_mode="messages")

    loop 툴 호출이 필요한 경우
        G->>OR: chat_node → LLM 호출
        OR-->>G: tool_call 응답
        G->>T: ToolNode 실행
        T-->>G: 툴 결과 반환
    end

    G->>OR: chat_node → 최종 LLM 호출
    OR-->>G: 토큰 스트리밍
    G-->>V: chunk (langgraph_node="chat")
    V-->>B: data: {"delta": "..."}\n\n
    V-->>B: data: [DONE]\n\n
```

---

## 3. 심층 분석 워크플로우 (/api/analyze)

LangGraph 그래프를 사용하지 않고 Python 코드로 직접 오케스트레이션하는 5단계 파이프라인.

```mermaid
flowchart TD
    Input["종목명 입력\n(예: 삼성전자)"]

    subgraph Step0["Step 0 · 티커 변환"]
        Resolve["resolve_ticker()\n① 하드코딩 딕셔너리\n② 6자리 숫자 → .KS\n③ 한글 → 네이버 자동완성 API\n④ 그대로 사용 (미국 주식)"]
    end

    subgraph Parallel["Step 1 + 1.5 + 2 (병렬 실행 — ThreadPoolExecutor)"]
        Quant["Step 1 · 정량 데이터\ncompute_quant()\n· MA20 / MA60 / MA120\n· 이격도 (gap20)\n· 거래량 변화율\n· 14일 낙폭\n· ATR14 / 손절가\n· 지지선 / 저항선"]
        Regime["Step 1.5 · 시장 레짐\ndetect_market_regime()\n· KOSPI 추세 (+2/0/-2)\n· 거래량 변화 (+2/0/-2)\n· 원화 환율 프록시 (+2/0/-2)\n· VIX 수준 (+2/0/-2)\n· 고점 대비 낙폭 (+2/0/-2)\n· 연속 하락일 (+2/0/-2)\n→ 합산 점수 → 시장 상태"]
        News["Step 2 · 정성 데이터\nDuckDuckGo Search\n뉴스 5건 수집"]
    end

    subgraph Step4["Step 3~4 · LLM 리포트 생성"]
        Prompt["build_analysis_prompt()\n정량 + 레짐 + 뉴스 조합"]
        LLM["gpt-oss-20b (OpenRouter)\nmax_tokens=2800\n스트리밍 출력\n\n출력 구조:\n① 시장 레짐 요약\n② 핵심 정량 요약\n③ 3 페르소나 투자 의견\n   (개미·기관·외국인)\n④ 손절 기준 테이블\n⑤ 안전마진 / 최악 시나리오"]
    end

    SSE["SSE 스트리밍\nstatus → meta → delta 토큰"]

    Input --> Step0
    Step0 --> Parallel
    Parallel --> Step4
    Prompt --> LLM
    LLM --> SSE
```

### 시장 레짐 점수 체계

```mermaid
graph LR
    Score{{"종합 점수\n-12 ~ +12"}}

    Score -->|"+7 이상"| S1["🟢 강세장\nRisk 2.5% / 2.2×ATR"]
    Score -->|"+3 ~ +6"| S2["🟢 상승 추세\nRisk 2.0% / 2.0×ATR"]
    Score -->|"-2 ~ +2"| S3["🟡 경계\nRisk 1.5% / 1.8×ATR"]
    Score -->|"-6 ~ -3"| S4["🟠 전환\nRisk 1.0% / 1.5×ATR"]
    Score -->|"-7 이하"| S5["🔴 약세장\nRisk 0% 매수 금지"]
```

---

## 4. 정기 리포트 파이프라인

```mermaid
sequenceDiagram
    participant GH as GitHub Actions\n(매일 23:00 UTC)
    participant R as Render /generate-all
    participant SB as Supabase
    participant YF as yfinance
    participant OR as OpenRouter
    participant RS as Resend

    GH->>R: POST X-Cron-Secret: goTdj
    R->>SB: 활성 구독자 조회\n(active=true, send_hour=8)
    SB-->>R: [{email, tickers}, ...]

    loop 구독자별 반복
        R->>YF: detect_market_regime()
        R->>YF: compute_quant(ticker) × N (병렬)
        R->>OR: generate_one_liner() × N (병렬)
        OR-->>R: 한줄 AI 코멘트
        R->>RS: send_email(HTML 템플릿)
        RS-->>R: {id: "..."}
        R->>SB: report_logs INSERT
    end

    R-->>GH: {sent: N, total: N}
```

---

## 5. 상태(State) 구조

```mermaid
classDiagram
    class ChatState {
        +messages: Annotated[list, add_messages]
    }

    class QuantData {
        +ticker: str
        +currency: str
        +price: float
        +ma20 / ma60 / ma120: float
        +gap20: float
        +below_ma20: bool
        +vol_change: float
        +drawdown14: float
        +support1 / resistance1: float
        +atr14: float
        +atr_stop: float
    }

    class RegimeData {
        +score: int
        +state: str
        +risk_limit: str
        +atr_buffer: str
        +constraint: str
        +kospi: float
        +vix: float
        +checks: dict
    }

    class Subscription {
        +id: uuid
        +email: str
        +tickers: list[str]
        +send_hour: int
        +active: bool
        +created_at: timestamptz
    }

    ChatState --> QuantData : analyze 워크플로우에서 생성
    ChatState --> RegimeData : analyze 워크플로우에서 생성
    Subscription --> RegimeData : 리포트 생성 시 참조
```

---

## 6. 도구(Tool) 명세

| 도구 | 호출 시점 | 구현 |
|------|----------|------|
| `web_search(query)` | 뉴스·이슈 검색 필요 시 | DuckDuckGo DDGS (max 5건) |
| `get_current_date()` | 날짜·시각 질문 시 | `datetime.now()` |
| `get_price(ticker)` | 단일 종목 시세 조회 | yfinance `fast_info` |
| `get_multiple_prices(tickers)` | 복수 종목 일괄 조회 | yfinance 반복 호출 |

> 위 4개 툴은 LangGraph `ToolNode`에 자동 등록되며, LLM이 `tool_call`을 포함한 응답을 반환하면 `tools_condition`이 감지해 자동 실행합니다.

---

## 7. 파일 구조

```
stockchat/
├── api/
│   ├── index.py          # Vercel 서버리스 진입점 (Flask + LangGraph)
│   └── index.html        # 프론트엔드 (Vanilla JS + marked.js)
│
├── server/
│   ├── app.py            # Render API 서버 (정기 리포트)
│   ├── cron_report.py    # GitHub Actions Cron 진입점
│   ├── requirements.txt
│   ├── Procfile
│   └── render.yaml
│
├── .github/
│   └── workflows/
│       └── daily-report.yml  # 매일 08:00 KST 크론
│
├── requirements.txt      # Vercel 의존성
├── vercel.json
└── README.md
```
