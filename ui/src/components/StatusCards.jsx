export default function StatusCards({ vehicles = [], missions = [], events = [] }) {
  const running = vehicles.filter(v => v.operatingstate === 2).length
  const errors  = vehicles.filter(v => v.operatingstate === 6).length
  const active  = missions.filter(m => m.transportstate === 7).length

  const cards = [
    { label: '운행 중 차량',    value: running,        color: 'var(--color-text-info)'    },
    { label: '진행 중 미션',    value: active,         color: 'var(--color-text-success)'  },
    { label: 'PLC 신호 (금일)', value: events.length,  color: 'var(--color-text-primary)'  },
    { label: '차량 오류',       value: errors,         color: 'var(--color-text-danger)'   },
  ]

  return (
    <div style={{
      display              : 'grid',
      gridTemplateColumns  : 'repeat(4, 1fr)',
      gap                  : '10px',
      marginBottom         : '20px',
    }}>
      {cards.map(c => (
        <div key={c.label} style={{
          background   : 'var(--color-background-secondary, #f9fafb)',
          borderRadius : 'var(--border-radius-md, rgba(0,0,0,0.08))',
          padding      : '12px 14px',
        }}>
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary, #6b7280)', marginBottom: '4px' }}>
            {c.label}
          </div>
          <div style={{ fontSize: '22px', fontWeight: 500, color: c.color }}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  )
}