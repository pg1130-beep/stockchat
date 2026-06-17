import { useState, useRef, useEffect } from 'react'
import MarkdownRenderer from './MarkdownRenderer'

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 3 }}>
      <span style={{ fontSize: 10, color: '#6b7280', padding: '0 4px' }}>
        {isUser ? '나' : 'MarketBot'}
      </span>
      <div style={{
        maxWidth: '92%',
        padding: '10px 14px',
        borderRadius: 14,
        borderBottomRightRadius: isUser ? 3 : 14,
        borderBottomLeftRadius: isUser ? 14 : 3,
        background: isUser ? '#4f8ef7' : '#1a1d27',
        border: isUser ? 'none' : '1px solid #2a2d3e',
        fontSize: 13,
      }}>
        {isUser
          ? <span style={{ whiteSpace: 'pre-wrap', color: '#fff' }}>{msg.content}</span>
          : <MarkdownRenderer content={msg.content} />
        }
      </div>
    </div>
  )
}

function Thinking() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 3 }}>
      <span style={{ fontSize: 10, color: '#6b7280', padding: '0 4px' }}>MarketBot</span>
      <div style={{
        padding: '10px 14px', borderRadius: 14, borderBottomLeftRadius: 3,
        background: '#1a1d27', border: '1px solid #2a2d3e',
        display: 'flex', gap: 4, alignItems: 'center',
      }}>
        <span style={{ fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>분석 중</span>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            width: 4, height: 4, borderRadius: '50%',
            background: '#6b7280', display: 'inline-block',
            animation: `blink 1.2s ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  )
}

export default function ChatPanel({ messages, loading, onSend, onClear }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function handleSubmit(e) {
    e.preventDefault()
    if (!input.trim() || loading) return
    onSend(input)
    setInput('')
  }

  const canSend = !loading && input.trim().length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0f1117' }}>
      <style>{`@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }`}</style>

      {/* 채팅 헤더 */}
      <div style={{
        padding: '14px 16px', background: '#1a1d27',
        borderBottom: '1px solid #2a2d3e', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14 }}>💬</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#e8eaf0' }}>AI 상담</span>
          <span style={{
            background: '#00c896', color: '#000',
            fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 20,
          }}>LIVE</span>
        </div>
        <button onClick={onClear} style={{
          background: 'none', border: '1px solid #2a2d3e',
          color: '#6b7280', padding: '4px 10px', borderRadius: 6,
          cursor: 'pointer', fontSize: 11,
        }}>초기화</button>
      </div>

      {/* 메시지 영역 */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '16px 14px',
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        {messages.length === 0 && (
          <div style={{ color: '#6b7280', fontSize: 13, textAlign: 'center', margin: 'auto', lineHeight: 1.8 }}>
            왼쪽 빠른 분석 버튼을 누르거나<br />
            직접 질문을 입력해보세요.
          </div>
        )}
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {loading && <Thinking />}
        <div ref={bottomRef} />
      </div>

      {/* 입력 */}
      <form onSubmit={handleSubmit} style={{
        padding: '12px 14px', background: '#1a1d27',
        borderTop: '1px solid #2a2d3e', flexShrink: 0,
        display: 'flex', gap: 8,
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="종목, 시황, 투자 질문..."
          style={{
            flex: 1, background: '#0f1117', border: '1px solid #2a2d3e',
            color: '#e8eaf0', padding: '9px 12px', borderRadius: 10,
            fontSize: 13, outline: 'none',
          }}
          onFocus={e => e.target.style.borderColor = '#4f8ef7'}
          onBlur={e => e.target.style.borderColor = '#2a2d3e'}
        />
        <button type="submit" disabled={!canSend} style={{
          background: canSend ? '#4f8ef7' : '#2a2d3e',
          color: canSend ? '#fff' : '#6b7280',
          border: 'none', padding: '9px 16px', borderRadius: 10,
          cursor: canSend ? 'pointer' : 'not-allowed',
          fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
        }}>전송</button>
      </form>
    </div>
  )
}
