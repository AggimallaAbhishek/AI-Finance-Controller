import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

function App() {
  const [status, setStatus] = useState('checking backend...')

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data) => setStatus(`backend says: ${data.status}`))
      .catch(() => setStatus('backend unreachable'))
  }, [])

  return (
    <main style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>AI Finance Controller</h1>
      <p>{status}</p>
    </main>
  )
}

export default App
