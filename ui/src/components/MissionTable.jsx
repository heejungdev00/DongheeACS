const TRANSPORT_STATE = {
  0 : { label: '신규',        color: 'var(--color-text-secondary, #6b7280)' },
  1 : { label: '수락됨',      color: 'var(--color-text-info, #2563eb)'      },
  3 : { label: '배정됨',      color: 'var(--color-text-info, #2563eb)'      },
  7 : { label: '이동 중',     color: 'var(--color-text-success, #16a34a)'   },
  8 : { label: '완료',        color: 'var(--color-text-success, #16a34a)'   },
  9 : { label: '취소됨',      color: 'var(--color-text-danger, #dc2626)'    },
  10: { label: '오류',        color: 'var(--color-text-danger, #dc2626)'    },
}

export default function MissionTable({ data = [], onRefresh }) {
  const createMission = async () => {
  try {
    const response = await fetch('/api/missions/create', {
      method: 'POST',
            
    });

    const res = await response.json();
    if (response.ok) {
      console.log("실제 data 변수의 내용", res);
      const missionID = res.payload?.acceptedmissions?.[0] ?? 'unknown'
      alert(`미션 생성 성공! ID: ${missionID}`)
      if (onRefresh) onRefresh()
    } else {
      alert(`미션 생성 실패: ${res.detail || res.message}`);
    }
  } catch (error) {
    console.error("Error creating mission:", error)
    alert('서버 통신 오류')
  }
};







  // 모든 미션 취소 함수
  const handleCancelAll = async () => {
    if (!window.confirm("정말로 모든 미션을 취소하시겠습니까? 이 작업은 되돌릴 수 없습니다.")) {
      return;
    }

    try {
      const response = await fetch('/api/missions/cancel-all', {
        method: 'POST',
      });

      if (response.ok) {
        alert("모든 미션에 취소 요청을 보냈습니다.");
        if (onRefresh) onRefresh();
      } else {
        const errorData = await response.json();
        alert(`취소 실패: ${errorData.message || '알 수 없는 오류'}`);
      }
    } catch (error) {
      console.error("API 호출 중 에러:", error);
      alert("서버와 통신하는 중 오류가 발생했습니다.");
    }
  };

// 특정 미션의 추적/재생성 로직을 완전히 삭제
  const handleDeleteTracking = async (missionId) => {
    if (!window.confirm(`미션 #${missionId}의 추적을 삭제하시겠습니까?\n\n자동 재생성이 중지되고 추적 목록에서 제거됩니다.\n(ANT 서버의 실제 미션 상태는 그대로 유지됩니다)`)) {
      return
    }

    try {
      const response = await fetch(`/api/tracking/${missionId}`, {
        method: 'DELETE',
      })

      const res = await response.json()
      if (response.ok) {
        alert(`미션 #${missionId} 추적 삭제 완료`)
        if (onRefresh) onRefresh()
      } else if (response.status === 404) {
        alert(`미션 #${missionId}은 추적 중인 미션이 아닙니다.`)
      } else {
        alert(`삭제 실패: ${res.detail || res.message}`)
      }
    } catch (error) {
      console.error("Error deleting mission tracking:", error)
      alert('서버 통신 오류')
    }
  }


  if (data.length === 0) {
    return (
      <div style={{ color: 'var(--color-text-secondary)', fontSize: '13px', padding: '16px 0' }}>
        미션 데이터가 없습니다. ANT server 연결을 확인하세요.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      
      {/* 버튼 영역 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
        {/* <button 
          onClick={createMission}
          style={{ backgroundColor: '#4CAF50', color: 'white', padding: '10px 20px', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          ➕ 테스트 미션 생성
        </button> */}

        <button 
          onClick={handleCancelAll}
          style={cancelButtonStyle}
        >
          모든 미션 취소
        </button>
      </div>

      {/* 테이블 영역 */}
      <div style={{ border: '0.5px solid var(--color-border-tertiary)', borderRadius: 'var(--border-radius-md)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', tableLayout: 'fixed' }}>
          <thead>
            <tr style={{ background: 'var(--color-background-secondary)' }}>
              {['미션 ID', '상태', '출발', '도착', '페이로드', '배정 차량', '작업'].map(h => (
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 500,
                  fontSize: '11px', color: 'var(--color-text-secondary)',
                  borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((m, i) => {
              const s = TRANSPORT_STATE[m.transportstate] ?? { label: '-', color: 'var(--color-text-secondary, #6b7280)' }
              return (
                <tr key={m.missionid} style={{
                  background: i % 2 === 0 ? 'var(--color-background-primary, #ffffff)' : 'var(--color-background-secondary, #f9fafb)'
                }}>
                  <td style={td}>#{m.missionid}</td>
                  <td style={td}><span style={{ color: s.color, fontWeight: 500 }}>{s.label}</span></td>
                  <td style={td}>{m.fromnode || '—'}</td>
                  <td style={td}>{m.tonode   || '—'}</td>
                  <td style={td}>{m.payload  || '—'}</td>
                  <td style={td}>{m.assignedto || '—'}</td>
                  <td style={td}>
                    <button
                    onClick={() => handleDeleteTracking(m.missionid)}
                    style={stopRetryButtonStyle}
                    >
                      🛑 재생성 중지/삭제
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
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

const cancelButtonStyle = {
  backgroundColor: 'transparent',
  color: 'var(--color-text-danger, #dc2626)',
  border: '1px solid var(--color-text-danger, #dc2626)',
  borderRadius: '4px',
  padding: '6px 12px',
  fontSize: '12px',
  fontWeight: '600',
  cursor: 'pointer',
  transition: 'all 0.2s ease',
  outline: 'none',
}

const stopRetryButtonStyle = {
  backgroundColor: 'transparent',
  color: 'var(--color-text-warning, #d97706)',
  border: '1px solid var(--color-text-warning, #d97706)',
  borderRadius: '4px',
  padding: '4px 8px',
  fontSize: '11px',
  fontWeight: '600',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
}