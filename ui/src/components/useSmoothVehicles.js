import { useEffect, useRef, useState } from "react"

const lerp = (a, b, t) => a + (b - a) * t

// 360도 경계 각도 보간 (최단 거리 방향 계산)
const lerpAngle = (a, b, t) => {
  let diff = (b - a) % (Math.PI * 2)
  if (diff < -Math.PI) diff += Math.PI * 2
  if (diff > Math.PI) diff -= Math.PI * 2
  return a + diff * t
}

export function useSmoothVehicles(targetVehicles, pollInterval = 500) {
  const [smoothVehicles, setSmoothVehicles] = useState([])
  const stateRef = useRef(new Map())

  useEffect(() => {
    const now = performance.now()

    targetVehicles.forEach(target => {
      const prev = stateRef.current.get(target.name)
      const newCoord = target.location?.coord
      const newCourse = target.location?.course ?? 0

      if (!prev || !newCoord) {
        stateRef.current.set(target.name, {
          fromCoord: newCoord || [0, 0],
          toCoord: newCoord || [0, 0],
          fromCourse: newCourse,
          toCourse: newCourse,
          startTime: now,
          raw: target
        })
      } else {
        // 새 신호 수신 시: '현재 실제로 이동 중이던 순간 좌표'를 계산해서 새 출발점으로 설정
        const elapsed = now - prev.startTime
        const progress = elapsed / pollInterval

        const currentX = lerp(prev.fromCoord[0], prev.toCoord[0], progress)
        const currentY = lerp(prev.fromCoord[1], prev.toCoord[1], progress)
        const currentCourse = lerpAngle(prev.fromCourse, prev.toCourse, progress)

        stateRef.current.set(target.name, {
          fromCoord: [currentX, currentY],
          toCoord: newCoord,
          fromCourse: currentCourse,
          toCourse: newCourse,
          startTime: now,
          raw: target
        })
      }
    })
  }, [targetVehicles, pollInterval])

  useEffect(() => {
    let animId

    const update = () => {
      const now = performance.now()
      const updated = []

      stateRef.current.forEach((data) => {
        const elapsed = now - data.startTime
        // 💡 핵심: 복잡한 이징을 빼고, 진행률(progress)을 위치와 각도에 1:1로 똑같이 적용합니다.
        const progress = elapsed / pollInterval

        const x = lerp(data.fromCoord[0], data.toCoord[0], progress)
        const y = lerp(data.fromCoord[1], data.toCoord[1], progress)
        const course = lerpAngle(data.fromCourse, data.toCourse, progress)

        updated.push({
          ...data.raw,
          location: {
            ...data.raw.location,
            coord: [x, y],
            course: course
          }
        })
      })

      setSmoothVehicles(updated)
      animId = requestAnimationFrame(update)
    }

    animId = requestAnimationFrame(update)
    return () => cancelAnimationFrame(animId)
  }, [pollInterval])

  return smoothVehicles
}