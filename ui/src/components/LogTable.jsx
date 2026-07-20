import React from 'react'

export default function LogTable({ data = [], events = [] }) {
  // DB 로그 + WebSocket 실시간 이벤트 합쳐서 표시
  const wsLogs = events
    .filter(e => e.type === 'mission_created' || e.type === 'error')
    .map((e, i) => ({
      id        : `ws-${i}`,
      created   : new Date().toLocaleTimeString(),
      // ── 수정: coil_address 대신 레지스터에서 계산된 mission_case 바인딩 ──
      mission_case: e.signal?.mission_case ?? '-',
      fromnode  : e.signal?.fromnode   ?? '-',
      tonode    : e.signal?.tonode || e.signal?.tostation || '-',
      mission_id: e.result?.payload?.acceptedmissions?.[0] ?? null,
      success   : e.type === 'mission_created' ? 1 : 0,
      realtime  : true,
    }))

  // 백엔드 db.py 구조와 맞추기 위해 데이터 키 매핑 통일 (from_node ➔ fromnode)
  const rows = [...wsLogs, ...data.map(d => ({
    ...d,
    mission_case: d.mission_case ?? d.coil_addr ?? '-' // 과도기 데이터 호환용
  }))].slice(0, 100)

  if (rows.length === 0) {
    return (
      <div style={{ color: 'var(--color-text-secondary, #6b7280)', fontSize: '13px', padding: '16px 0' }}>
        PLC 트리거 로그가 없습니다.
      </div>
    )
  }

  return (
    <div style={{ border: '0.5px solid var(--color-border-tertiary)', borderRadius: 'var(--border-radius-md)', overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', tableLayout: 'fixed' }}>
        <thead>
          <tr style={{ background: 'var(--color-background-secondary)' }}>
            {/* ── 수정: 헤더 명칭 '코일' ➔ '케이스' 변경 ── */}
            {['시각', '케이스', '출발 노드', '도착 노드', '미션 ID', '결과'].map(h => (
              <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 500,
                fontSize: '11px', color: 'var(--color-text-secondary)',
                borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} style={{
              background: r.realtime
                ? 'var(--color-background-info)'
                : i % 2 === 0
                  ? 'var(--color-background-primary)'
                  : 'var(--color-background-secondary)',
            }}>
              <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                {r.created?.slice(0, 19) ?? '-'}
              </td>
              {/* ── 수정: mission_case 표시 ── */}
              <td style={td}>
                {r.mission_case !== '-' ? `Case ${r.mission_case}` : '-'}
              </td>
              <td style={td}>{r.fromnode ?? r.from_node ?? '-'}</td>
              <td style={td}>{r.tonode ?? r.to_node ?? '-'}</td>
              <td style={td}>{r.mission_id ? `#${r.mission_id}` : '—'}</td>
              <td style={td}>
                <span style={{
                  fontSize  : '11px',
                  fontWeight: 500,
                  color     : r.success
                    ? 'var(--color-text-success)'
                    : 'var(--color-text-danger)',
                }}>
                  {r.success ? '성공' : '실패'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const td = {
  padding      : '8px 12px',
  borderBottom : '0.5px solid var(--color-border-tertiary)',
  overflow     : 'hidden',
  textOverflow : 'ellipsis',
  whiteSpace   : 'nowrap',
}