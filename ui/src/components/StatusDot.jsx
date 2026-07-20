export default function StatusDot({ connected, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '7px', fontSize: '12px' }}>
      <span style={{
        width       : '7px',
        height      : '7px',
        borderRadius: '50%',
        background  : connected
          ? 'var(--color-background-success, #22c55e)'
          : 'var(--color-background-danger, #ef4444)',
        flexShrink  : 0,
      }} />
      <span style={{ color: 'var(--color-text-secondary, #6b7280)' }}>{label}</span>
    </div>
  )
}