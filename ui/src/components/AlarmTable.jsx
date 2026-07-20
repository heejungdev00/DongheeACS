// state: 0=Active, 1=Acknowledged, 2=Closed, 3=Deleted
const ALARM_STATE = {
  0: { label: '활성',    bg: '#fee2e2', color: '#dc2626' },
  1: { label: '확인됨',  bg: '#fef9c3', color: '#92400e' },
  2: { label: '종료',    bg: '#dcfce7', color: '#16a34a' },
  3: { label: '삭제됨',  bg: '#f3f4f6', color: '#6b7280' },
}

// eventname 기준 심각도 색상
function getSeverityColor(eventname = '') {
  if (eventname.includes('critical')) return '#dc2626'
  if (eventname.includes('error'))    return '#ea580c'
  if (eventname.includes('warning'))  return '#ca8a04'
  return '#6b7280'
}

function getSeverityLabel(eventname = '') {
  if (eventname.includes('critical')) return 'CRITICAL'
  if (eventname.includes('error'))    return 'ERROR'
  if (eventname.includes('warning'))  return 'WARNING'
  return 'INFO'
}

function formatTime(isoStr) {
  if (!isoStr) return '-'
  try {
    return new Date(isoStr).toLocaleString('ko-KR')
  } catch {
    return isoStr
  }
}

const thStyle = {
  padding     : '8px 12px',
  textAlign   : 'left',
  fontWeight  : 500,
  fontSize    : '11px',
  color       : '#6b7280',
  background  : '#f9fafb',
  borderBottom: '1px solid rgba(0,0,0,0.08)',
  whiteSpace  : 'nowrap',
}

const tdStyle = {
  padding     : '8px 12px',
  borderBottom: '1px solid rgba(0,0,0,0.06)',
  fontSize    : '12px',
  overflow    : 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace  : 'nowrap',
}

export default function AlarmTable({ data = [] }) {
  if (data.length === 0) {
    return (
      <p style={{ color: '#6b7280', fontSize: '13px', padding: '16px 0' }}>
        알람이 없습니다.
      </p>
    )
  }

  return (
    <div style={{
      border      : '1px solid rgba(0,0,0,0.08)',
      borderRadius: '8px',
      overflow    : 'hidden',
    }}>
      <table style={{
        width          : '100%',
        borderCollapse : 'collapse',
        tableLayout    : 'fixed',
      }}>
        <colgroup>
          <col style={{ width: '100px'  }} />  {/* 심각도 */}
          <col style={{ width: '90px'  }} />  {/* 상태 */}
          <col style={{ width: '90px'  }} />  {/* 차량 */}
          <col style={{ width: '200px' }} />  {/* 이벤트 */}
          <col style={{ width: '200px' }} />  {/* 마지막 발생 */}
          <col style={{ width: '50px'  }} />  {/* 횟수 */}
        </colgroup>
        <thead>
          <tr>
            {['level', 'state', '차량', '이벤트', '마지막 발생', '횟수'].map(h => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((alarm, i) => {
            const stateInfo   = ALARM_STATE[alarm.state] ?? ALARM_STATE[3]
            const sevColor    = getSeverityColor(alarm.eventname)
            const sevLabel    = getSeverityLabel(alarm.eventname)

            return (
              <tr key={alarm.uuid ?? i} style={{
                background: alarm.state === 0
                  ? '#fff5f5'                                   // 활성 알람 강조
                  : i % 2 === 0 ? '#ffffff' : '#f9fafb',
              }}>

                {/* 심각도 */}
                <td style={tdStyle}>
                  <span style={{
                    fontSize    : '10px',
                    fontWeight  : 600,
                    padding     : '2px 6px',
                    borderRadius: '4px',
                    background  : sevColor + '20',
                    color       : sevColor,
                  }}>
                    {sevLabel}
                  </span>
                </td>

                {/* 상태 */}
                <td style={tdStyle}>
                  <span style={{
                    fontSize    : '11px',
                    fontWeight  : 500,
                    padding     : '2px 8px',
                    borderRadius: '20px',
                    background  : stateInfo.bg,
                    color       : stateInfo.color,
                  }}>
                    {stateInfo.label}
                  </span>
                </td>

                {/* 차량 */}
                <td style={{ ...tdStyle, fontWeight: 500 }}>
                  {alarm.sourceid || '-'}
                </td>

                {/* 이벤트명 */}
                <td style={{
                  ...tdStyle,
                  fontSize  : '13px',
                  color     : '#374151',
                }}>
                  {alarm.eventname || '-'}
                </td>

                {/* 마지막 발생 */}
                <td style={{ ...tdStyle, color: '#6b7280' }}>
                  {formatTime(alarm.lasteventat)}
                </td>

                {/* 발생 횟수 */}
                <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 500 }}>
                  {alarm.eventcount ?? '-'}
                </td>

              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}