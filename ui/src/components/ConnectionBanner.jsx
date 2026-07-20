export default function ConnectionBanner({ status }) {
  const issues = []

  if (!status.plc) issues.push(`PLC (${status.plc_host})`)
  if (!status.ant) issues.push(`ANT server (${status.ant_host})`)

  if (issues.length === 0) return null

  return (
    <div style={{
      background : 'var(--color-background-warning, #fef9c3)',
      border     : '0.5px solid var(--color-border-warning, #fbbf24)',
      borderRadius: 'var(--border-radius-md)',
      padding    : '10px 16px',
      marginBottom: '16px',
      display    : 'flex',
      alignItems : 'center',
      gap        : '10px',
    }}>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 2L14 13H2L8 2Z"
          stroke="var(--color-text-warning)"
          strokeWidth="1.2" fill="none"/>
        <line x1="8" y1="7" x2="8" y2="10"
          stroke="var(--color-text-warning)" strokeWidth="1.2"/>
        <circle cx="8" cy="11.5" r="0.6"
          fill="var(--color-text-warning)"/>
      </svg>
      <span style={{ fontSize: '13px', color: 'var(--color-text-warning, #92400e)' }}>
        연결 안 됨: <strong>{issues.join(', ')}</strong>
        &nbsp;— 자동으로 재연결을 시도합니다.
      </span>
    </div>
  )
}