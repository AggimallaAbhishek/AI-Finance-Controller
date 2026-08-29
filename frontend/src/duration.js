// Shared by ReconcileProgress (live elapsed/ETA while a run is in flight)
// and Overview (the frozen duration_seconds a completed run persisted) so
// "1m 30s" reads the same way in both places.
export function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.round(seconds))
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  if (m === 0) return `${s}s`
  return `${m}m ${s}s`
}
