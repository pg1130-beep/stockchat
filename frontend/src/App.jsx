import { useState, useRef, useEffect, useCallback } from 'react'
import MarketPanel from './MarketPanel'
import ChatPanel from './ChatPanel'

export default function App() {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  async function send(text) {
    const trimmed = text.trim()
    if (!trimmed || loading) return
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

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#0f1117' }}>
      {/* 왼쪽 2/3 — 시황 대시보드 */}
      <div style={{ flex: 2, display: 'flex', flexDirection: 'column', borderRight: '1px solid #2a2d3e', minWidth: 0 }}>
        <MarketPanel onAskChat={send} />
      </div>

      {/* 오른쪽 1/3 — 채팅 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 320 }}>
        <ChatPanel
          messages={messages}
          loading={loading}
          onSend={send}
          onClear={() => setMessages([])}
        />
      </div>
    </div>
  )
}
