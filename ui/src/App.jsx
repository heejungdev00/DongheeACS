import { useState }          from 'react'
import { useWebSocket }      from './hooks/useWebSocket'
import { usePolling }        from './hooks/usePolling'
import { getVehicles, getMissions, getLogs, getAlarms } from './api/client'
import ConnectionBanner      from './components/ConnectionBanner'
import StatusDot             from './components/StatusDot'
import StatusCards           from './components/StatusCards'
import VehicleTable          from './components/VehicleTable'
import MissionTable          from './components/MissionTable'
import LogTable              from './components/LogTable'
import AlarmTable            from './components/AlarmTable'
import MapViewer             from './components/MapViewer'

const TABS = [
  { key: 'vehicles', label: '차량 현황' },
  { key: 'missions', label: '미션 현황' },
  { key: 'logs',     label: 'PLC 로그'  },
  { key: 'alarms',   label: '알람 로그' },
  { key: 'map',      label: '맵 뷰어'   },
]

export default function App() {
  const [tab, setTab]             = useState('vehicles')
  const { events, connStatus }    = useWebSocket()
  const { data: vehicles }        = usePolling(getVehicles, 3000)
  const { data: missions }        = usePolling(getMissions, 3000)
  const { data: logs }            = usePolling(getLogs,     5000)
  const { data: alarms }          = usePolling(getAlarms, 10000)

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'sans-serif' }}>

      {/* 사이드바 */}
      <aside style={{
        width       : '180px',
        background  : 'var(--color-background-secondary)',
        borderRight : '0.5px solid var(--color-border-tertiary)',
        display     : 'flex',
        flexDirection: 'column',
        padding     : '0',
      }}>
        <div style={{ padding: '16px', fontWeight: 500, fontSize: '15px',
          borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
          ANT 미들웨어
        </div>

        <nav style={{ padding: '12px 0', flex: 1 }}>
          {TABS.map(t => (
            <div key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding    : '8px 16px',
                cursor     : 'pointer',
                fontSize   : '13px',
                fontWeight : tab === t.key ? 500 : 400,
                color      : tab === t.key
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-secondary)',
                background : tab === t.key
                  ? 'var(--color-background-primary)'
                  : 'transparent',
                borderRight: tab === t.key
                  ? '2px solid var(--color-border-info)'
                  : '2px solid transparent',
              }}>
              {t.label}
              {/* 활성 알람 수 배지 */}
              {t.key === 'alarms' && alarms.filter(a => a.state === 0).length > 0 && (
                <span style={{
                  marginLeft  : '6px',
                  fontSize    : '10px',
                  fontWeight  : 600,
                  padding     : '1px 6px',
                  borderRadius: '20px',
                  background  : '#fee2e2',
                  color       : '#dc2626',
                }}>
                  {alarms.filter(a => a.state === 0).length}
                </span>
              )}
            </div>
          ))}
        </nav>

        {/* 연결 상태 표시 */}
        <div style={{ padding: '12px 16px',
          borderTop: '0.5px solid var(--color-border-tertiary)',
          display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)',
            marginBottom: '4px' }}>연결 상태</div>
          <StatusDot connected={connStatus.ant} label={`ANT server`} />
          <StatusDot connected={connStatus.plc} label={`PLC`} />
        </div>
      </aside>

      {/* 메인 */}
      <main style={{ flex: 1, padding: '24px', overflow: 'auto' }}>

        {/* 연결 문제 있을 때만 배너 표시 */}
        <ConnectionBanner status={connStatus} />

        <StatusCards vehicles={vehicles} missions={missions} events={events} />

        {/* 탭 */}
        <div style={{ display: 'flex', gap: '0',
          borderBottom: '0.5px solid var(--color-border-tertiary)',
          marginBottom: '16px' }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              style={{
                padding     : '8px 16px',
                background  : 'none',
                border      : 'none',
                borderBottom: tab === t.key
                  ? '2px solid #378ADD'
                  : '2px solid transparent',
                cursor      : 'pointer',
                fontSize    : '13px',
                fontWeight  : tab === t.key ? 500 : 400,
                color       : tab === t.key
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-secondary)',
              }}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'vehicles' && <VehicleTable data={vehicles} />}
        {tab === 'missions' && <MissionTable data={missions} />}
        {tab === 'logs'     && <LogTable data={logs} events={events} />}
        {tab === 'alarms'   && <AlarmTable data={alarms} />}
        {tab === 'map'      && <MapViewer/>}
      </main>
    </div>
  )
}