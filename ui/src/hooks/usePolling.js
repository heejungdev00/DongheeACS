import { useState, useEffect } from 'react'

export function usePolling(fetchFn, interval = 3000) {
  const [data, setData]     = useState([])
  const [error, setError]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = () =>
      fetchFn()
        .then(d  => { setData(d); setError(null); setLoading(false) })
        .catch(e => { setError(e.message) })

    fetch()
    const timer = setInterval(fetch, interval)
    return () => clearInterval(timer)
  }, [interval])

  return { data, error, loading }
}