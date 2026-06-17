import uuid
from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from chatbot import build_graph
from tools import get_system_prompt

load_dotenv()

app = Flask(__name__)
app.secret_key = "langgraph-market-secret"
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])

graph = build_graph("openrouter")
conversation_store: dict[str, list] = {}

HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarketBot — AI 시황 상담</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3e;
    --accent: #4f8ef7;
    --accent2: #00c896;
    --red: #f75050;
    --text: #e8eaf0;
    --muted: #6b7280;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); display: flex;
         flex-direction: column; height: 100vh; }

  /* 헤더 */
  header { display: flex; align-items: center; justify-content: space-between;
           padding: 14px 24px; background: var(--surface);
           border-bottom: 1px solid var(--border); flex-shrink: 0; }
  .logo { display: flex; align-items: center; gap: 10px; }
  .logo-icon { font-size: 22px; }
  .logo-text { font-size: 17px; font-weight: 700; letter-spacing: -0.3px; }
  .logo-sub { font-size: 11px; color: var(--muted); margin-top: 1px; }
  .badge { background: var(--accent2); color: #000; font-size: 10px;
           font-weight: 700; padding: 2px 7px; border-radius: 20px; }
  .clear-btn { background: none; border: 1px solid var(--border); color: var(--muted);
               padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; }
  .clear-btn:hover { border-color: var(--red); color: var(--red); }

  /* 빠른 질문 버튼 */
  .quick-wrap { padding: 10px 20px; display: flex; gap: 8px; flex-wrap: wrap;
                background: var(--surface); border-bottom: 1px solid var(--border);
                flex-shrink: 0; }
  .quick-btn { background: var(--bg); border: 1px solid var(--border); color: var(--text);
               padding: 5px 12px; border-radius: 20px; cursor: pointer; font-size: 12px; }
  .quick-btn:hover { border-color: var(--accent); color: var(--accent); }

  /* 메시지 영역 */
  #messages { flex: 1; overflow-y: auto; padding: 24px 20px;
              display: flex; flex-direction: column; gap: 16px; }
  #messages:empty::after {
    content: '시황 분석, 종목 조회, 투자 정보 등을 물어보세요.';
    color: var(--muted); font-size: 14px; text-align: center; margin: auto;
  }

  .msg-wrap { display: flex; flex-direction: column; gap: 4px; }
  .msg-wrap.user { align-items: flex-end; }
  .msg-wrap.ai { align-items: flex-start; }

  .sender { font-size: 11px; color: var(--muted); padding: 0 4px; }

  .msg { max-width: 75%; padding: 12px 16px; border-radius: 16px;
         line-height: 1.65; font-size: 14px; white-space: pre-wrap; word-break: break-word; }
  .user .msg { background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
  .ai .msg { background: var(--surface); border: 1px solid var(--border);
             border-bottom-left-radius: 4px; }
  .ai.thinking .msg { color: var(--muted); font-style: italic; }

  /* 타이핑 점 */
  .dots span { animation: blink 1.2s infinite; display: inline-block; }
  .dots span:nth-child(2) { animation-delay: .2s; }
  .dots span:nth-child(3) { animation-delay: .4s; }
  @keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }

  /* 입력 폼 */
  #form { display: flex; padding: 16px 20px; gap: 10px;
          background: var(--surface); border-top: 1px solid var(--border); flex-shrink: 0; }
  #input { flex: 1; background: var(--bg); border: 1px solid var(--border);
           color: var(--text); padding: 11px 16px; border-radius: 12px;
           font-size: 14px; outline: none; }
  #input:focus { border-color: var(--accent); }
  #input::placeholder { color: var(--muted); }
  #send-btn { background: var(--accent); color: #fff; border: none;
              padding: 11px 20px; border-radius: 12px; cursor: pointer;
              font-size: 14px; font-weight: 600; white-space: nowrap; }
  #send-btn:disabled { background: var(--border); color: var(--muted); cursor: not-allowed; }
</style>
</head>
<body>
<header>
  <div class="logo">
    <span class="logo-icon">📈</span>
    <div>
      <div class="logo-text">MarketBot</div>
      <div class="logo-sub">AI 시황 분석 · 종목 상담</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <span class="badge">LIVE</span>
    <button class="clear-btn" onclick="clearChat()">대화 초기화</button>
  </div>
</header>

<div class="quick-wrap">
  <button class="quick-btn" onclick="ask('나스닥, S&P500, 비트코인 지금 시세 알려줘')">📊 주요 지수·시세</button>
  <button class="quick-btn" onclick="ask('오늘 미국 증시 주요 뉴스 검색해줘')">📰 미국 증시 뉴스</button>
  <button class="quick-btn" onclick="ask('삼성전자, SK하이닉스 현재가 알려줘')">🇰🇷 국내 주요 종목</button>
  <button class="quick-btn" onclick="ask('현재 금 가격과 달러 인덱스 알려줘')">🥇 금·달러 시세</button>
  <button class="quick-btn" onclick="ask('NVDA 현재 시세와 최근 뉴스 분석해줘')">🔍 종목 심층 분석</button>
</div>

<div id="messages"></div>

<form id="form">
  <input id="input" placeholder="종목명, 시황, 투자 질문 등 무엇이든 물어보세요..." autocomplete="off" autofocus>
  <button type="submit" id="send-btn">전송</button>
</form>

<script>
  const messagesEl = document.getElementById('messages');
  const input = document.getElementById('input');
  const btn = document.getElementById('send-btn');

  function addMsg(role, text, isThinking=false) {
    const wrap = document.createElement('div');
    wrap.className = 'msg-wrap ' + role + (isThinking ? ' thinking' : '');

    const sender = document.createElement('div');
    sender.className = 'sender';
    sender.textContent = role === 'user' ? '나' : 'MarketBot';

    const div = document.createElement('div');
    div.className = 'msg';
    if (isThinking) {
      div.innerHTML = '분석 중<span class="dots"><span>.</span><span>.</span><span>.</span></span>';
    } else {
      div.textContent = text;
    }
    wrap.appendChild(sender);
    wrap.appendChild(div);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
  }

  async function sendMessage(text) {
    if (!text.trim()) return;
    input.value = '';
    btn.disabled = true;

    addMsg('user', text);
    const thinking = addMsg('ai', '', true);

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      const data = await res.json();
      thinking.remove();
      addMsg('ai', data.error ? '오류: ' + data.error : data.reply);
    } catch(e) {
      thinking.remove();
      addMsg('ai', '네트워크 오류가 발생했습니다.');
    }
    btn.disabled = false;
    input.focus();
  }

  function ask(text) { sendMessage(text); }

  document.getElementById('form').addEventListener('submit', e => {
    e.preventDefault();
    sendMessage(input.value);
  });

  async function clearChat() {
    await fetch('/clear', { method: 'POST' });
    messagesEl.innerHTML = '';
  }
</script>
</body>
</html>
"""

@app.route("/")
def index():
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    return render_template_string(HTML)


@app.route("/chat", methods=["POST"])
def chat():
    sid = session.get("sid")
    if not sid:
        return jsonify({"error": "세션 없음"}), 400

    user_text = request.json.get("message", "").strip()
    if not user_text:
        return jsonify({"error": "빈 메시지"}), 400

    if sid not in conversation_store:
        conversation_store[sid] = [SystemMessage(content=get_system_prompt())]

    history = conversation_store[sid]
    history.append(HumanMessage(content=user_text))

    try:
        result = graph.invoke({"messages": history})
        ai_msg = result["messages"][-1]
        history.append(ai_msg)
        return jsonify({"reply": ai_msg.content})
    except Exception as e:
        history.pop()
        return jsonify({"error": str(e)}), 500


@app.route("/clear", methods=["POST"])
def clear():
    sid = session.get("sid")
    if sid:
        conversation_store.pop(sid, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=8080)
