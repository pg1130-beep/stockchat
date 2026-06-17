import { useState, useEffect } from 'react'

const QUICK = [
  '나스닥, S&P500, 비트코인 오늘 시황 분석해줘',
  '오늘 미국 증시 주요 뉴스 알려줘',
  '삼성전자, SK하이닉스 현재 상황 어때?',
  'NVDA 최근 동향과 전망 알려줘',
]

function TickerCard({ item }) {
  if (item.error) return (
    <div style={card}>
      <div style={{ fontSize: 11, color: '#6b7280' }}>{item.label}</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>조회 실패</div>
    </div>
  )
  const up = item.change >= 0
  return (
    <div style={card}>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>{item.label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: '#fff', letterSpacing: '-0.3px' }}>
        {item.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>{item.currency}</span>
      </div>
      <div style={{ marginTop: 5, fontSize: 13, fontWeight: 600, color: up ? '#00c896' : '#f75050' }}>
        {up ? '▲' : '▼'} {Math.abs(item.change).toFixed(2)}%
      </div>
    </div>
  )
}

const card = {
  background: '#1a1d27',
  border: '1px solid #2a2d3e',
  borderRadius: 10,
  padding: '14px 16px',
  flex: '1 1 140px',
}

export default function MarketPanel({ onAskChat }) {
  const [tickers, setTickers] = useState([])
  const [memo, setMemo] = useState(() => localStorage.getItem('market-memo') || '')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  async function fetchMarket() {
    setRefreshing(true)
    try {
      const res = await fetch('/api/market')
      const data = await res.json()
      setTickers(data)
      setLastUpdated(new Date())
    } catch {}
    setRefreshing(false)
  }

  useEffect(() => {
    fetchMarket()
    const id = setInterval(fetchMarket, 60000) // 1분마다 갱신
    return () => clearInterval(id)
  }, [])

  function saveMemo(val) {
    setMemo(val)
    localStorage.setItem('market-memo', val)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* 헤더 */}
      <div style={{
        padding: '14px 20px', background: '#1a1d27',
        borderBottom: '1px solid #2a2d3e', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>📈</span>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>MarketBot</div>
            <div style={{ fontSize: 11, color: '#6b7280' }}>AI 시황 분석 · 종목 상담</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {lastUpdated && (
            <span style={{ fontSize: 11, color: '#6b7280' }}>
              {lastUpdated.toLocaleTimeString()} 기준
            </span>
          )}
          <button onClick={fetchMarket} disabled={refreshing} style={{
            background: 'none', border: '1px solid #2a2d3e', color: refreshing ? '#6b7280' : '#4f8ef7',
            padding: '5px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12,
          }}>
            {refreshing ? '갱신 중…' : '↻ 새로고침'}
          </button>
        </div>
      </div>

      {/* 스크롤 영역 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* 시세 카드 그리드 */}
        <section>
          <div style={sectionTitle}>주요 시세</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {tickers.length === 0
              ? Array(8).fill(0).map((_, i) => (
                  <div key={i} style={{ ...card, background: '#1a1d27', opacity: 0.4 }}>
                    <div style={{ height: 12, background: '#2a2d3e', borderRadius: 4, width: '60%', marginBottom: 8 }} />
                    <div style={{ height: 20, background: '#2a2d3e', borderRadius: 4, width: '80%', marginBottom: 8 }} />
                    <div style={{ height: 12, background: '#2a2d3e', borderRadius: 4, width: '40%' }} />
                  </div>
                ))
              : tickers.map(t => <TickerCard key={t.symbol} item={t} />)
            }
          </div>
        </section>

        {/* 빠른 질문 */}
        <section>
          <div style={sectionTitle}>빠른 분석 요청</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {QUICK.map(q => (
              <button key={q} onClick={() => onAskChat(q)} style={{
                background: '#1a1d27', border: '1px solid #2a2d3e', color: '#c8cadb',
                padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                fontSize: 13, textAlign: 'left', transition: 'border-color 0.15s',
              }}
              onMouseOver={e => e.currentTarget.style.borderColor = '#4f8ef7'}
              onMouseOut={e => e.currentTarget.style.borderColor = '#2a2d3e'}>
                → {q}
              </button>
            ))}
          </div>
        </section>

        {/* 시장 개요 요약 */}
        <section>
          <div style={sectionTitle}>시장 요약</div>
          <MarketSummary tickers={tickers} />
        </section>

      </div>

      {/* 메모 — 하단 고정 */}
      <div style={{
        borderTop: '1px solid #2a2d3e', padding: '14px 20px',
        background: '#1a1d27', flexShrink: 0,
      }}>
        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          📝 메모 (자동 저장)
        </div>
        <textarea
          value={memo}
          onChange={e => saveMemo(e.target.value)}
          placeholder="투자 아이디어, 주의 종목, 매매 계획 등을 자유롭게 메모하세요..."
          rows={5}
          style={{
            width: '100%', background: '#0f1117', border: '1px solid #2a2d3e',
            color: '#e8eaf0', padding: '10px 12px', borderRadius: 8,
            fontSize: 13, lineHeight: 1.6, resize: 'vertical',
            fontFamily: 'inherit', outline: 'none',
            boxSizing: 'border-box',
          }}
          onFocus={e => e.target.style.borderColor = '#4f8ef7'}
          onBlur={e => e.target.style.borderColor = '#2a2d3e'}
        />
      </div>
    </div>
  )
}

function MarketSummary({ tickers }) {
  if (tickers.length === 0) return null
  const sp = tickers.find(t => t.symbol === '^GSPC')
  const nq = tickers.find(t => t.symbol === '^IXIC')
  const btc = tickers.find(t => t.symbol === 'BTC-USD')
  const kospi = tickers.find(t => t.symbol === '^KS11')

  const items = [
    sp && { label: 'S&P 500', value: sp.change, desc: sp.change >= 0 ? '강세' : '약세' },
    nq && { label: 'NASDAQ', value: nq.change, desc: nq.change >= 0 ? '강세' : '약세' },
    btc && { label: 'BTC', value: btc.change, desc: btc.change >= 0 ? '상승세' : '하락세' },
    kospi && { label: 'KOSPI', value: kospi.change, desc: kospi.change >= 0 ? '강세' : '약세' },
  ].filter(Boolean)

  return (
    <div style={{ background: '#1a1d27', border: '1px solid #2a2d3e', borderRadius: 10, overflow: 'hidden' }}>
      {items.map((item, i) => (
        <div key={item.label} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '11px 16px',
          borderBottom: i < items.length - 1 ? '1px solid #1f2130' : 'none',
        }}>
          <span style={{ fontSize: 13, color: '#c8cadb' }}>{item.label}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, color: '#6b7280' }}>{item.desc}</span>
            <span style={{
              fontSize: 13, fontWeight: 700,
              color: item.value >= 0 ? '#00c896' : '#f75050',
              minWidth: 60, textAlign: 'right',
            }}>
              {item.value >= 0 ? '+' : ''}{item.value.toFixed(2)}%
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

const sectionTitle = {
  fontSize: 11, fontWeight: 600, color: '#6b7280',
  letterSpacing: '0.07em', textTransform: 'uppercase',
  marginBottom: 10,
}
