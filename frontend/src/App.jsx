import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const QUICK = [
  { label: '📊 주요 지수·시세', text: '나스닥, S&P500, 비트코인 지금 시세 알려줘' },
  { label: '📰 미국 증시 뉴스', text: '오늘 미국 증시 주요 뉴스 검색해줘' },
  { label: '🇰🇷 국내 주요 종목', text: '삼성전자, SK하이닉스 현재가 알려줘' },
  { label: '🥇 금·달러', text: '현재 금 가격과 달러 인덱스 알려줘' },
  { label: '🔍 NVDA 분석', text: 'NVDA 현재 시세와 최근 뉴스 분석해줘' },
]

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 4 }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', padding: '0 4px' }}>
        {isUser ? '나' : 'MarketBot'}
      </span>
      <div style={{
        maxWidth: '78%',
        padding: '12px 16px',
        borderRadius: 16,
        borderBottomRightRadius: isUser ? 4 : 16,
        borderBottomLeftRadius: isUser ? 16 : 4,
        background: isUser ? 'var(--accent)' : 'var(--surface)',
        border: isUser ? 'none' : '1px solid var(--border)',
        fontSize: 14,
        lineHeight: 1.65,
      }}>
        {isUser
          ? <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
          : <div className="md-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
        }
      </div>
    </div>
  )
}

function Thinking() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', padding: '0 4px' }}>MarketBot</span>
      <div style={{
        padding: '12px 16px', borderRadius: 16, borderBottomLeftRadius: 4,
        background: 'var(--surface)', border: '1px solid var(--border)',
        color: 'var(--muted)', fontSize: 14, display: 'flex', gap: 4, alignItems: 'center',
      }}>
        <span style={{ fontStyle: 'italic' }}>분석 중</span>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            display: 'inline-block', width: 5, height: 5, borderRadius: '50%',
            background: 'var(--muted)',
            animation: `blink 1.2s ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function send(text) {
    const trimmed = text.trim()
    if (!trimmed || loading) return
    setInput('')
    // 전송 전 현재 히스토리 스냅샷 (새 user 메시지 제외)
    const history = messages
    setMessages(prev => [...prev, { role: 'user', content: trimmed }])
    setLoading(true)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, history }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'ai',
        content: data.error ? `오류: ${data.error}` : data.reply,
      }])
    } catch {
      setMessages(prev => [...prev, { role: 'ai', content: '네트워크 오류가 발생했습니다.' }])
    }
    setLoading(false)
  }

  function clearChat() {
    setMessages([])
  }

  const canSend = !loading && input.trim().length > 0

  return (
    <>
      <style>{`@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }`}</style>

      {/* 헤더 */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 24px', background: 'var(--surface)',
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 22 }}>📈</span>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.3px' }}>MarketBot</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>AI 시황 분석 · 종목 상담</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            background: 'var(--accent2)', color: '#000',
            fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
          }}>LIVE</span>
          <button onClick={clearChat} style={{
            background: 'none', border: '1px solid var(--border)', color: 'var(--muted)',
            padding: '6px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13,
          }}>
            대화 초기화
          </button>
        </div>
      </header>

      {/* 빠른 질문 */}
      <div style={{
        padding: '10px 20px', display: 'flex', gap: 8, flexWrap: 'wrap',
        background: 'var(--surface)', borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        {QUICK.map(q => (
          <button key={q.label} onClick={() => send(q.text)} disabled={loading} style={{
            background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)',
            padding: '5px 12px', borderRadius: 20, cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: 12, opacity: loading ? 0.5 : 1,
          }}>
            {q.label}
          </button>
        ))}
      </div>

      {/* 메시지 영역 */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '24px 20px',
        display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        {messages.length === 0 && (
          <p style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', margin: 'auto' }}>
            시황 분석, 종목 조회, 투자 정보 등을 물어보세요.
          </p>
        )}
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {loading && <Thinking />}
        <div ref={bottomRef} />
      </div>

      {/* 입력 폼 */}
      <form
        onSubmit={e => { e.preventDefault(); send(input) }}
        style={{
          display: 'flex', padding: '16px 20px', gap: 10,
          background: 'var(--surface)', borderTop: '1px solid var(--border)', flexShrink: 0,
        }}
      >
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="종목명, 시황, 투자 질문 등 무엇이든 물어보세요..."
          style={{
            flex: 1, background: 'var(--bg)', border: '1px solid var(--border)',
            color: 'var(--text)', padding: '11px 16px', borderRadius: 12,
            fontSize: 14, outline: 'none',
          }}
        />
        <button type="submit" disabled={!canSend} style={{
          background: canSend ? 'var(--accent)' : 'var(--border)',
          color: canSend ? '#fff' : 'var(--muted)',
          border: 'none', padding: '11px 20px', borderRadius: 12,
          cursor: canSend ? 'pointer' : 'not-allowed',
          fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap',
          transition: 'background 0.2s',
        }}>
          전송
        </button>
      </form>
    </>
  )
}
