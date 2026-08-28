import { useRef, useState } from 'react'
import { uploadAndReconcile } from './api'
import { useReconcileJob } from './useReconcileJob'
import ReconcileProgress from './ReconcileProgress'
import { BankIcon, CheckCircleIcon, UploadIcon } from './Icons'

function DropZone({ id, title, icon, format, file, onSelect, disabled }) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) onSelect(dropped)
  }

  return (
    <div
      className={`drop-zone${dragOver ? ' drop-zone--dragover' : ''}${file ? ' drop-zone--filled' : ''}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
      }}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept=".csv"
        className="sr-only"
        disabled={disabled}
        onChange={(e) => onSelect(e.target.files[0] || null)}
      />
      {file ? (
        <>
          <span className="drop-zone__icon drop-zone__icon--done">
            <CheckCircleIcon />
          </span>
          <h3>{file.name}</h3>
          <p className="drop-zone__hint muted">{(file.size / 1024).toFixed(0)} KB selected — click to replace.</p>
        </>
      ) : (
        <>
          <span className="drop-zone__icon">{icon}</span>
          <h3>{title}</h3>
          <p className="drop-zone__hint muted">Drag &amp; drop or click to browse.</p>
        </>
      )}
      <div className="drop-zone__format">
        <span className="drop-zone__format-label">Expected Format</span>
        <code>{format}</code>
      </div>
    </div>
  )
}

export default function UploadRunner({ onComplete }) {
  const [settlementFile, setSettlementFile] = useState(null)
  const [bankFile, setBankFile] = useState(null)
  const { job, start, running } = useReconcileJob(onComplete)

  function run() {
    start(() => uploadAndReconcile(settlementFile, bankFile))
  }

  return (
    <div className="upload-runner">
      <div className="upload-runner__zones">
        <DropZone
          id="settlement-file"
          title="Settlement CSV"
          icon={<UploadIcon />}
          format="txn_id, amount, currency, timestamp, merchant_ref"
          file={settlementFile}
          onSelect={setSettlementFile}
          disabled={running}
        />
        <DropZone
          id="bank-file"
          title="Bank Statement CSV"
          icon={<BankIcon />}
          format="post_date, description, debit, credit, balance"
          file={bankFile}
          onSelect={setBankFile}
          disabled={running}
        />
      </div>

      <div className="upload-runner__actions">
        <span className="muted">Files must be CSV format.</span>
        <button
          type="button"
          className="reconcile-runner__button"
          onClick={run}
          disabled={running || !settlementFile || !bankFile}
        >
          {running ? 'Running…' : 'Run Engine'}
        </button>
      </div>

      <ReconcileProgress job={job} variant="stepper" />
    </div>
  )
}
