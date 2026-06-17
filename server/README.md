# StockChat API 서버 (Render)

신규 기능을 위한 별도 API 서버. Vercel 앱(`../api/index.py`)의 기존 기능은 그대로 유지되고,
앞으로의 기능은 여기에 추가한다. 상시 구동 서버라 Vercel의 60초 제한·콜드스타트·번들 제약이 없다.

## 로컬 실행
```bash
cd server
pip install -r requirements.txt
python app.py          # http://localhost:8000
curl http://localhost:8000/api/v2/ping
```

## Render 배포 (GitHub 연동)
1. [render.com](https://render.com) → **New → Web Service**
2. 이 GitHub repo(`pg1130-beep/stockchat`) 선택
3. 설정:
   - **Root Directory**: `server`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --workers 2 --threads 4 --timeout 120`
   - **Plan**: Free
4. 필요한 환경변수(OPENROUTER_API_KEY 등)를 **Environment** 탭에 추가
5. **Create Web Service** → 배포 완료 후 URL 확인 (예: `https://stockchat-api.onrender.com`)

> `render.yaml`이 있으므로 **New → Blueprint**로 연결하면 위 설정이 자동 적용된다.

## 프론트엔드에서 호출
새 기능은 이 서버 URL로 호출한다 (CORS는 `app.py`의 `ALLOWED_ORIGINS`에 Vercel 도메인 등록됨):
```js
fetch('https://stockchat-api.onrender.com/api/v2/...')
```

## 신규 기능 추가
`app.py`의 "신규 기능은 아래에 추가하세요" 구역에 라우트를 추가한다.
무거운 의존성(yfinance, langchain 등)이 필요하면 `requirements.txt`에 추가 — Render는 번들 크기 제한이 없다.
```
