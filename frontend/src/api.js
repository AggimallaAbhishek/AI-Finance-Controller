const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

async function request(path) {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export function getRuns() {
  return request('/runs')
}

export function getExceptions(runId) {
  return request(`/exceptions?run_id=${encodeURIComponent(runId)}`)
}

export function getTrace(recordId, runId) {
  return request(`/audit/${encodeURIComponent(recordId)}?run_id=${encodeURIComponent(runId)}`)
}

export async function askQuestion(question, runId) {
  const res = await fetch(`${API_BASE}/qa`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, run_id: runId }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}
