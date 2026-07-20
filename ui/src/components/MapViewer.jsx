import { useEffect, useRef, useState, useCallback } from "react"
import { getVehicles } from "../api/client"
import { useSmoothVehicles } from './useSmoothVehicles'

const api = (url) => fetch(url).then(r => r.json())

// ANT 좌표계 → SVG 픽셀 변환
function useTransform(nodes, svgW, svgH, padding = 40) {
  return useCallback((x, y) => {
    if (!nodes.length) return [0, 0]
    const xs = nodes.map(n => n.x)
    const ys = nodes.map(n => n.y)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    const scaleX = (svgW - padding * 2) / (maxX - minX || 1)
    const scaleY = (svgH - padding * 2) / (maxY - minY || 1)
    const scale  = Math.min(scaleX, scaleY)
    return [
      padding + (x - minX) * scale,
      svgH - padding - (y - minY) * scale,  // Y축 반전
    ]
  }, [nodes, svgW, svgH, padding])
}

export default function MapViewer() {
  const [nodes,    setNodes]    = useState([])  // {id, name, x, y}
  const [links,    setLinks]    = useState([])  // {x1,y1,x2,y2}
  const [vehicles, setVehicles] = useState([])
  const [size,     setSize]     = useState({ w: 800, h: 600 })
  const containerRef = useRef(null)

  const smoothVehicles = useSmoothVehicles(vehicles, 2000)

  // 컨테이너 크기 추적
  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setSize({ w: width, h: Math.max(height, 400) })
    })
    if (containerRef.current) obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  // 맵 데이터 로드 (최초 1회)
  useEffect(() => {
  api("/api/map").then(mapList => {
    if (!mapList?.length) return

    const parsedNodes = []
    const parsedLinks = []

    mapList.forEach(mapItem => {
      const layers = mapItem?.data?.layers || []

      layers.forEach(layer => {
        if (layer.name === "navigation") {

          // ── 노드 파싱 ──────────────────────────────
          layer.symbols?.forEach(sym => {
            if (sym.symbolid === "node") {
              parsedNodes.push({
                id  : sym.id,
                name: sym.name,
                x   : sym.coord[0],
                y   : sym.coord[1],
              })
            }
          })

          // ── 링크 파싱 (중복 제거) ──────────────────
          // ids: [fromNodeId, toNodeId]
          const seen = new Set()
          layer.lines?.forEach(line => {
            const key = `${line.ids[0]}-${line.ids[1]}`
            const rev = `${line.ids[1]}-${line.ids[0]}`
            if (seen.has(key) || seen.has(rev)) return
            seen.add(key)
            parsedLinks.push({
              x1: line.coord[0],
              y1: line.coord[1],
              x2: line.coord[2],
              y2: line.coord[3],
              fromId: line.ids[0],
              toId  : line.ids[1],
            })
          })
        }
      })
    })

    setNodes(parsedNodes)
    setLinks(parsedLinks)
  }).catch(e => console.error("맵 로드 실패", e))
}, [])

  // 차량 위치 폴링 (2초)
  useEffect(() => {
    const poll = async () => {
      try {
        const data = await api("/api/vehicles")
        if (Array.isArray(data)) setVehicles(data)
      } catch {}
    }
    poll()
    const id = setInterval(poll, 500)
    return () => clearInterval(id)
  }, [])

  const toSVG = useTransform(nodes, size.w, size.h)

  // 노드 ID → 좌표 맵
  const nodeCoords = {}
    nodes.forEach(n => {
    const pos = toSVG(n.x, n.y)
    nodeCoords[n.id]   = pos  // 숫자 ID (path 배열용)
    nodeCoords[n.name] = pos  // 노드 이름 (디버깅용)
  })

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "500px", background: "#f8fafc",
               border: "1px solid #e2e8f0", borderRadius: "8px",
               overflow: "hidden", position: "relative" }}
    >
      <svg width={size.w} height={size.h}>

        {/* ── 링크 (경로선) ──────────────────────── */}
        {links.map((l, i) => {
          const [sx, sy] = toSVG(l.x1, l.y1)
          const [ex, ey] = toSVG(l.x2, l.y2)
          return (
            <line key={i} x1={sx} y1={sy} x2={ex} y2={ey}
              stroke="#cbd5e1" strokeWidth={1.5} />
          )
        })}

        {/* ── 차량 주행 경로 하이라이트 ──────────── */}
        {vehicles.map(v => {
            const path = v.path || []
            return path.map((nodeId, i) => {
                if (i === 0) return null
                const from = nodeCoords[path[i-1]]
                const to   = nodeCoords[nodeId]
                if (!from || !to) return null
                return (
                <line key={`path-${v.name}-${i}`}
                    x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]}
                    stroke="#3b82f6" strokeWidth={3}
                    strokeDasharray="6 3" opacity={0.8} />
                )
            })
        })}

        {/* ── 노드 ───────────────────────────────── */}
        {nodes.map(n => {
          const [sx, sy] = toSVG(n.x, n.y)
          return (
            <g key={n.id}>
              <circle cx={sx} cy={sy} r={4}
                fill="#94a3b8" stroke="#fff" strokeWidth={1} />
              <text x={sx+6} y={sy+4} fontSize={9} fill="#64748b">
                {n.name}
              </text>
            </g>
          )
        })}

        {/* ── 차량 위치 및 실시간 형상 ────────────── */}
        {smoothVehicles.map(v => {
          const coord = v.location?.coord
          if (!coord) return null
          
          // 1. 차량 중심축의 SVG 픽셀 좌표 계산
          const [sx, sy] = toSVG(coord[0], coord[1])
          const course   = v.location?.course || 0
          
          // 2. 스케일 계산 (1미터가 몇 픽셀인지 동적 산출 - 회전 처리에 필수)
          let scale = 1
          if (nodes.length > 1) {
            const xs = nodes.map(n => n.x)
            const minX = Math.min(...xs), maxX = Math.max(...xs)
            scale = (size.w - 80) / (maxX - minX || 1) // useTransform의 스케일 산출법 추적
          }

          // 3. body.shape 원본 로우 배열 파싱 -> SVG용 string ("x,y x,y ...") 팩토리 변환
          // ANT 좌표계의 상대좌표를 SVG 픽셀 스케일 크기로 변환하며 Y축 방향을 고려합니다.
          const bodyShapeArray = v.state?.["body.shape"] || []
          const pointsString = []
          for (let i = 0; i < bodyShapeArray.length; i += 2) {
            const rx = bodyShapeArray[i] * scale
            const ry = -bodyShapeArray[i+1] * scale // SVG 내부 상대 축 반전 처리
            pointsString.push(`${rx},${ry}`)
          }
          const finalPoints = pointsString.join(" ")

          const color = v.operatingstate === 6 ? "#ef4444"
                      : v.operatingstate === 2 ? "#22c55e"
                      : "#f59e0b"

          return (
            <g key={v.name}>
              {/* 💡 translate로 차량 정위치 맵핑 후, rotate로 라디안->디그리 회전 매핑 */}
              <g transform={`translate(${sx},${sy}) rotate(${-course * 180 / Math.PI})`}>
                {/* 폼 팩터 다각형(body.shape) 주입 */}
                {finalPoints ? (
                  <polygon points={finalPoints}
                    fill={color} stroke="#fff" strokeWidth={1.5} opacity={0.85} />
                ) : (
                  // 예외 상황 대비 폴백 삼각형
                  <polygon points="0,-12 8,8 -8,8" fill={color} stroke="#fff" strokeWidth={1.5} />
                )}
                {/* 헤딩 방향 전면 식별선 (필요시 활성화) */}
                <line x1={0} y1={0} x2={12} y2={0} stroke="#fff" strokeWidth={1.5} opacity={0.5} />
              </g>
            </g>
          )
        })}
      </svg>

      {/* 범례 */}
      <div style={{ position: "absolute", bottom: 8, right: 8,
                    background: "rgba(255,255,255,0.9)",
                    padding: "6px 10px", borderRadius: 6,
                    fontSize: 11, display: "flex", gap: 12 }}>
        <span><span style={{color:"#22c55e"}}>▲</span> 운행중</span>
        <span><span style={{color:"#f59e0b"}}>▲</span> 대기</span>
        <span><span style={{color:"#ef4444"}}>▲</span> 오류</span>
        <span style={{color:"#3b82f6"}}>— 주행경로</span>
      </div>
    </div>
  )
}