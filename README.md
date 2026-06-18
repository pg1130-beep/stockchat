# MarketBot — AI 시황 상담 서비스

실시간 시세 데이터와 AI 분석을 결합한 금융 시장 상담 웹 애플리케이션.

🌐 **서비스 URL**: https://stockchat-kappa.vercel.app

---

## 주요 기능

### 💬 AI 상담 채팅
- 종목·시황·투자 질문을 자유롭게 입력하면 AI가 실시간 스트리밍으로 답변
- 웹 검색 도구로 최신 뉴스·공시 반영
- 현재 날짜·시각 자동 인식
- 답변을 카카오톡으로 공유하는 버튼 제공

### 📊 페르소나 심층 분석 리포트
종목명 하나를 입력하면 5단계 워크플로우를 자동 실행:

| 단계 | 내용 |
|------|------|
| Step 1 | yfinance 실측 정량 데이터 (MA20/60/120, 이격도, ATR14, 거래량 변화율, 지지·저항) |
| Step 1.5 | 시장 레짐 감지 — 6개 지표 종합점수(-12~+12) → 강세/약세 판단 |
| Step 2 | 뉴스·목표주가 정성 데이터 수집 |
| Step 3~4 | 3가지 페르소나(개미·기관·외국인) 투자 의견서 |
| Step 4.5~4.7 | 손절 기준(ATR 기반) + 안전마진 테이블 |

### 📈 실시간 시세 대시보드
- KOSPI, NASDAQ, S&P500, BTC 등 주요 지수 실시간 가격
- 한글 종목명 자동 변환 (네이버 자동완성 API 사용)
- 빠른 분석 버튼 (시황, 뉴스, 특정 종목 즉시 질문)

### 📝 메모
- 투자 아이디어, 주의 종목, 매매 계획 메모
- Supabase DB에 자동 저장 (여러 기기에서 공유)

### 📧 정기 리포트 구독
- 이메일 + 관심종목 등록
- 매일 08:00 KST 자동 발송
- 이메일에 시장 레짐 요약 + 종목별 현재가·MA20·ATR·AI 코멘트 포함

---

## 기술 스택

### 프론트엔드 (Vercel)
| 항목 | 내용 |
|------|------|
| 언어 | HTML + Vanilla JS |
| 렌더링 | marked.js (마크다운 → HTML) |
| 통신 | SSE (Server-Sent Events) 스트리밍 |
| UI | 3패널 레이아웃 (시세 2/3 + 채팅 1/3), 모바일 탭바 지원 |

### 메인 API 서버 (Vercel Serverless)
| 항목 | 내용 |
|------|------|
| 프레임워크 | Flask (Python) |
| AI | LangGraph + OpenRouter (`gpt-oss-120b:free` / `gpt-oss-20b:free`) |
| 시장 데이터 | yfinance |
| 검색 | DuckDuckGo Search |
| DB | Supabase (메모 저장) |

### 신규 기능 API 서버 (Render)
| 항목 | 내용 |
|------|------|
| 프레임워크 | Flask + gunicorn |
| 이메일 | Resend SDK |
| 스케줄러 | GitHub Actions (매일 23:00 UTC) |
| DB | Supabase (구독 정보·발송 로그) |

---

## 아키텍처

```
사용자 브라우저
    │
    ├─── Vercel (프론트 + 메인 API)
    │       api/index.html   — UI
    │       api/index.py     — /api/chat, /api/analyze, /api/market, /api/memo
    │
    └─── Render (신규 기능 API)
            server/app.py    — /api/v2/report/*
                │
                ├── Supabase  (subscriptions, report_logs, memos 테이블)
                ├── Resend    (이메일 발송)
                └── OpenRouter (AI 한줄 코멘트)

GitHub Actions (매일 08:00 KST)
    └─── POST /api/v2/report/generate-all → Render → 전체 구독자 이메일 발송
```

---

## API 엔드포인트

### Vercel (`https://stockchat-kappa.vercel.app`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/chat` | AI 채팅 (SSE 스트리밍) |
| POST | `/api/analyze` | 심층 분석 워크플로우 (SSE 스트리밍) |
| GET | `/api/market` | 주요 지수 시세 일괄 조회 |
| GET/POST | `/api/memo` | 공유 메모 조회/저장 |

### Render (`https://stockchat-kka8.onrender.com`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v2/report/subscribe` | 리포트 구독 등록/수정 |
| GET | `/api/v2/report/subscription` | 구독 현황 조회 |
| DELETE | `/api/v2/report/subscription` | 구독 취소 |
| POST | `/api/v2/report/preview` | 리포트 즉시 생성 (발송 없음) |
| POST | `/api/v2/report/send-test` | 테스트 이메일 발송 |
| POST | `/api/v2/report/generate-all` | 전체 구독자 일괄 발송 (Cron 전용) |

---

## 환경변수

### Vercel
```
OPENROUTER_API_KEY   # OpenRouter API 키
SUPABASE_URL         # Supabase 프로젝트 URL
SUPABASE_KEY         # Supabase service_role 키
```

### Render
```
OPENROUTER_API_KEY   # OpenRouter API 키
RESEND_API_KEY       # Resend API 키
RESEND_FROM          # 발신 주소 (기본: onboarding@resend.dev)
RENDER_EXTERNAL_URL  # 이 서버의 외부 URL
SUPABASE_URL         # Supabase 프로젝트 URL
SUPABASE_KEY         # Supabase service_role 키
CRON_SECRET          # GitHub Actions 인증 토큰
```

### GitHub Actions Secret
```
CRON_SECRET          # Render 서버 인증용 (Render의 값과 동일)
```

---

## 로컬 실행

```bash
# 메인 서버 (Vercel 앱)
pip install -r requirements.txt
cp .env.example .env   # API 키 입력
python local_app.py    # http://localhost:8080

# 신규 기능 서버 (Render 앱)
cd server
pip install -r requirements.txt
python app.py          # http://localhost:8000
```

---

## 데이터베이스 스키마 (Supabase)

```sql
-- 공유 메모
CREATE TABLE memos (
  id      text PRIMARY KEY,
  content text NOT NULL DEFAULT ''
);

-- 리포트 구독
CREATE TABLE subscriptions (
  id         uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  email      text NOT NULL UNIQUE,
  tickers    text[] NOT NULL DEFAULT '{}',
  send_hour  int  NOT NULL DEFAULT 8,
  active     boolean NOT NULL DEFAULT true,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- 발송 로그
CREATE TABLE report_logs (
  id        uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  email     text NOT NULL,
  tickers   text[] NOT NULL,
  status    text NOT NULL,   -- 'ok' | 'error'
  error_msg text,
  sent_at   timestamptz DEFAULT now()
);
```

---

## 주의사항

- 모든 투자 정보는 참고용이며 투자 권유가 아닙니다
- Render 무료 플랜은 15분 미사용 시 슬립 → 첫 요청 약 30초 지연
- Vercel 서버리스 60초 타임아웃 — 심층 분석은 병렬 처리로 40초 내 완료
- `onboarding@resend.dev` 발신 주소는 본인 이메일로만 테스트 발송 가능
