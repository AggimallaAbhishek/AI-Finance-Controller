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

export function getMatches(runId) {
  return request(`/matches?run_id=${encodeURIComponent(runId)}`)
}

export function getTrace(recordId, runId) {
  return request(`/audit/${encodeURIComponent(recordId)}?run_id=${encodeURIComponent(runId)}`)
}

export async function startReconcileAsync() {
  const res = await fetch(`${API_BASE}/reconcile/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export function getReconcileStatus(jobId) {
  return request(`/reconcile/status/${encodeURIComponent(jobId)}`)
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

export async function resolveException(recordId, { resolution, note, matchedRecordId }, runId) {
  const url = `${API_BASE}/exceptions/${encodeURIComponent(recordId)}/resolve?run_id=${encodeURIComponent(runId)}`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution, note, matched_record_id: matchedRecordId || null }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}
