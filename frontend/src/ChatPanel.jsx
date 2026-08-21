import { useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { askQuestion } from './api'

const SUGGESTIONS = [
  'What is the match rate?',
  'Why is today’s payout short?',
  'Show unmatched bank entries over ₹1000',
]

const MARKDOWN_COMPONENTS = {
  table: ({ children }) => (
    <div className="chat-msg__table-wrap">
      <table>{children}</table>
    </div>
  ),
}

export default function ChatPanel({ runId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const listRef = useRef(null)

  async function send(question) {
    const text = question ?? input
    if (!text.trim() || sending) return

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setInput('')
    setSending(true)

    try {
      const res = await askQuestion(text, runId)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.answer, sourcedFrom: res.sourced_from },
      ])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Sorry, I couldn't reach the Q&A agent: ${e.message}`, isError: true },
      ])
    } finally {
      setSending(false)
      requestAnimationFrame(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
      })
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    send()
  }

  return (
    <aside className="chat-panel" aria-label="Ask about this batch">
      <h2>Ask about this batch</h2>

      <div className="chat-panel__messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="chat-panel__empty">
            <p className="muted">Ask a question grounded in this run's data.</p>
            <div className="chat-panel__suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} disabled={sending}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg--${m.role}${m.isError ? ' chat-msg--error' : ''}`}>
            {m.role === 'assistant' ? (
              <div className="chat-msg__markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                  {m.content}
                </ReactMarkdown>
              </div>
            ) : (
              <p>{m.content}</p>
            )}
            {m.sourcedFrom?.length > 0 && (
              <div className="chat-msg__sources">
                {m.sourcedFrom.map((id) => (
                  <code key={id}>{id}</code>
                ))}
              </div>
            )}
          </div>
        ))}

        {sending && (
          <div className="chat-msg chat-msg--assistant chat-msg--pending" aria-live="polite">
            <span className="typing-dots">
              <span />
              <span />
              <span />
            </span>
          </div>
        )}
      </div>

      <form className="chat-panel__input" onSubmit={handleSubmit}>
        <label htmlFor="chat-input" className="sr-only">
          Ask a question
        </label>
        <input
          id="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. how many exceptions this batch?"
          disabled={sending}
          autoComplete="off"
        />
        <button type="submit" disabled={sending || !input.trim()}>
          Send
        </button>
      </form>
    </aside>
  )
}
