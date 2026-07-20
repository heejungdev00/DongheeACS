import { useEffect, useRef, useState } from 'react'

export function useWebSocket() {
  const [events, setEvents]       = useState([])
  const [connStatus, setConnStatus] = useState({
    plc: false,
    ant: false,
    plc_host: '',
    ant_host: '',
  })
  const wsRef = useRef(null)

  const connect = () => {
    const ws = new WebSocket(`ws://${location.host}/ws`)

    ws.onopen = () => {
      console.log("WebSocket 연결 성공");
    };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      console.log("WS Received:", data);

      if (data.type === 'connection_status') {
        setConnStatus(prev => ({
          ...prev,
          plc: data.status.plc,
          ant: data.status.ant,
          plc_host: data.status.plc_host,
          ant_host: data.status.ant_host
        }));
        return;
      }
      
      setEvents(prev => [data, ...prev].slice(0, 200))
    }

    ws.onclose = () => setTimeout(connect, 3000)
    wsRef.current = ws
  }

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [])

  return { events, connStatus }
}