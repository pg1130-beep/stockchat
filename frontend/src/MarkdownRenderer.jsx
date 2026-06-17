import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const tableStyle = {
  wrapper: {
    overflowX: 'auto',
    margin: '12px 0',
    borderRadius: 8,
    border: '1px solid #2a2d3e',
  },
  table: {
    borderCollapse: 'collapse',
    width: '100%',
    fontSize: 13,
    minWidth: 300,
  },
  th: {
    background: '#222538',
    color: '#c8cadb',
    padding: '8px 14px',
    textAlign: 'left',
    fontWeight: 600,
    fontSize: 12,
    letterSpacing: '0.04em',
    borderBottom: '1px solid #2a2d3e',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '8px 14px',
    borderBottom: '1px solid #1f2130',
    color: '#e8eaf0',
    whiteSpace: 'nowrap',
  },
  tdEven: {
    background: 'rgba(255,255,255,0.02)',
  },
}

function colorize(text) {
  if (typeof text !== 'string') return text
  if (text.includes('+') && (text.includes('%') || text.match(/\+[\d,.]+/))) {
    return <span style={{ color: '#00c896', fontWeight: 600 }}>{text}</span>
  }
  if (text.includes('-') && (text.includes('%') || text.match(/-[\d,.]+/))) {
    return <span style={{ color: '#f75050', fontWeight: 600 }}>{text}</span>
  }
  return text
}

const components = {
  table: ({ children }) => (
    <div style={tableStyle.wrapper}>
      <table style={tableStyle.table}>{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  th: ({ children }) => <th style={tableStyle.th}>{children}</th>,
  tr: ({ children, node }) => {
    // tbody의 tr인지 판별
    const isBody = node?.position?.start && node.children?.some(c => c.tagName === 'td')
    return <tr style={isBody ? {} : {}}>{children}</tr>
  },
  td: ({ children, node }) => {
    const text = typeof children === 'string' ? children : ''
    return <td style={tableStyle.td}>{colorize(text) || children}</td>
  },

  p: ({ children }) => (
    <p style={{ margin: '6px 0', lineHeight: 1.7 }}>{children}</p>
  ),
  strong: ({ children }) => (
    <strong style={{ color: '#fff', fontWeight: 700 }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ color: '#9ca3b0' }}>{children}</em>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{
      borderLeft: '3px solid #4f8ef7',
      paddingLeft: 12,
      margin: '10px 0',
      color: '#9ca3b0',
      fontStyle: 'italic',
    }}>{children}</blockquote>
  ),
  ul: ({ children }) => (
    <ul style={{ paddingLeft: 18, margin: '6px 0' }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ paddingLeft: 18, margin: '6px 0' }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ margin: '4px 0', lineHeight: 1.6 }}>{children}</li>
  ),
  code: ({ inline, children }) =>
    inline
      ? <code style={{
          background: '#222538', color: '#a5b4fc',
          padding: '2px 6px', borderRadius: 4,
          fontSize: 12, fontFamily: 'monospace',
        }}>{children}</code>
      : <pre style={{
          background: '#222538', padding: 14,
          borderRadius: 8, overflowX: 'auto',
          margin: '10px 0', fontSize: 12,
          fontFamily: 'monospace', lineHeight: 1.6,
        }}><code>{children}</code></pre>,
  h1: ({ children }) => <h1 style={{ fontSize: 18, fontWeight: 700, margin: '12px 0 6px', color: '#fff' }}>{children}</h1>,
  h2: ({ children }) => <h2 style={{ fontSize: 16, fontWeight: 700, margin: '10px 0 5px', color: '#e8eaf0' }}>{children}</h2>,
  h3: ({ children }) => <h3 style={{ fontSize: 14, fontWeight: 600, margin: '8px 0 4px', color: '#c8cadb' }}>{children}</h3>,
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid #2a2d3e', margin: '12px 0' }} />,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer"
       style={{ color: '#4f8ef7', textDecoration: 'none' }}>
      {children}
    </a>
  ),
}

export default function MarkdownRenderer({ content }) {
  return (
    <div style={{ fontSize: 14, lineHeight: 1.65, color: '#e8eaf0' }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
