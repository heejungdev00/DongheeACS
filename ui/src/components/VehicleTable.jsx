import React, { useState } from 'react'; 

const STATE = {
  0: { label: '미삽입',   bg: 'var(--color-background-secondary, #f3f4f6)', color: 'var(--color-text-secondary, #6b7280)' },
  1: { label: '대기',     bg: 'var(--color-background-success, #dcfce7)',   color: 'var(--color-text-success, #16a34a)'   },
  2: { label: '운행 중',  bg: 'var(--color-background-info, #dbeafe)',      color: 'var(--color-text-info, #2563eb)'      },
  3: { label: '사용불가', bg: 'var(--color-background-danger, #fee2e2)',    color: 'var(--color-text-danger, #dc2626)'    },
  4: { label: '일시정지', bg: 'var(--color-background-warning, #fef9c3)',   color: 'var(--color-text-warning, #92400e)'   },
  5: { label: '슬립',     bg: 'var(--color-background-secondary, #f3f4f6)', color: 'var(--color-text-secondary, #6b7280)' },
  6: { label: '오류',     bg: 'var(--color-background-danger, #fee2e2)',    color: 'var(--color-text-danger, #dc2626)'    },
}

function Badge({ stateId }) {
  const s = STATE[stateId] ?? STATE[0]
  return (
    <span style={{
      fontSize     : '11px',
      padding      : '2px 8px',
      borderRadius : '20px',
      fontWeight   : 500,
      background   : s.bg,
      color        : s.color,
    }}>
      {s.label}
    </span>
  )
}

export default function VehicleTable({ data = [] }) {
  const [loading, setLoading] = useState(false);

  //강제 삽입 api 호출 함수
  const handleForceInsert = async () => {
    if (!window.confirm('차량 강제 삽입을 진행하시겠습니까')) return;

    setLoading(true);
    try {
      const response = await fetch('/api/vehicles/forceinsert', {
        method: 'POST'
      });
      if (response.ok) {
        // 💡 백엔드가 리턴한 리스트 데이터 파싱 (예: [] 또는 ['에러메시지'])
        const resultList = await response.json();

        // 2. 받아온 배열의 길이를 '정확하게' 체크합니다.
        if (resultList && resultList.length > 0) {
          // 리스트에 뭐가 들어있다면 무조건 에러가 있는 실패 상황!
          const errorMsg = resultList[0] || '알 수 없는 장비 에러';
          alert(`❌ 강제 삽입 실패: ${errorMsg}`);
        } else {
          // 리스트가 완벽히 비어있어야([]) 성공 상황!
          alert('✅ 강제 삽입 명령 전송 완료');
        }
        
      } else {
        alert('❌ 명령 전송 실패 (서버 오류)');
      }
    } catch (error) {
      console.error('Force Insert Error:', error);
      alert('❌ 통신 에러가 발생했습니다.')
    } finally {
      setLoading(false);
    }
  };
  
  if (data.length === 0) {
    return (
      <div style={{ color: 'var(--color-text-secondary, #6b7280)', fontSize: '13px', padding: '16px 0' }}>
        차량 데이터가 없습니다. ANT server 연결을 확인하세요.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      
      {/* 버튼 영역 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
        <button 
          onClick={handleForceInsert}
          style={{ backgroundColor: '#4CAF50', color: 'white', padding: '10px 20px', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          ➕ Force Insert
        </button>
      </div>

      {/* 테이블 영역 */}
      <div style={{ border: '0.5px solid var(--color-border-tertiary, rgba(0,0,0,0.08))', borderRadius: 'var(--border-radius-md)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', tableLayout: 'fixed' }}>
          <thead>
            <tr style={{ background: 'var(--color-background-secondary)' }}>
              {['차량명', '상태', '배터리', '현재 미션 ID', '현재 노드'].map(h => (
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 500,
                  fontSize: '11px', color: 'var(--color-text-secondary)',
                  borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((v, i) => (
              <tr key={v.name} style={{
                background: i % 2 === 0 ? 'var(--color-background-primary, #ffffff)' : 'var(--color-background-secondary, #f9fafb)'
              }}>
                <td style={td}>{v.name}</td>
                <td style={td}><Badge stateId={v.operatingstate} /></td>
                <td style={td}>{v.state?.['battery.info']?.[0] ?? '-'}%</td>
                <td style={td}>{v.missionid || '—'}</td>
                <td style={td}>{v.location?.currentnode?.name ?? '-'}</td>
              </tr>
            ))}
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