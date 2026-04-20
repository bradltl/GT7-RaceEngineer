import { useEffect, useMemo, useState } from 'react'
import type { DashboardState, EngineerMessage } from './types'

const emptyState: DashboardState = {
  latest_message: null,
  recent_messages: [],
  metrics: {
    connection_state: 'unknown',
    source_mode: 'unknown',
  },
}

export default function App() {
  const [state, setState] = useState<DashboardState>(emptyState)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let active = true

    fetch('http://127.0.0.1:8000/api/state')
      .then((response) => response.json())
      .then((json: DashboardState) => {
        if (active) setState(json)
      })
      .catch(() => {
        // Replay mode can still work after ingest starts; keep the shell visible.
      })

    const socket = new WebSocket('ws://127.0.0.1:8000/ws')
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
    socket.onmessage = (event) => {
      try {
        setState(JSON.parse(event.data) as DashboardState)
      } catch {
        // Ignore malformed payloads rather than breaking the dashboard.
      }
    }

    return () => {
      active = false
      socket.close()
    }
  }, [])

  const recent = useMemo(() => [...state.recent_messages].reverse(), [state.recent_messages])

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">GT7 Race Engineer</p>
          <h1>Deterministic race signals, not chat.</h1>
        </div>
        <div className={`status ${connected ? 'online' : 'offline'}`}>
          {connected ? 'Websocket connected' : 'Websocket offline'}
        </div>
      </section>

      <section className="grid">
        <article className="card emphasis">
          <h2>Current Callout</h2>
          <div className="message">
            {state.latest_message?.text ?? 'Waiting for telemetry...'}
          </div>
          <div className="meta">
            {state.latest_message ? `${state.latest_message.priority.toUpperCase()} • ${state.latest_message.category}` : 'No message yet'}
          </div>
        </article>

        <article className="card">
          <h2>Connection</h2>
          <dl>
            <div><dt>State</dt><dd>{state.metrics.connection_state}</dd></div>
            <div><dt>Source</dt><dd>{state.metrics.source_mode}</dd></div>
            <div><dt>Stale</dt><dd>{state.metrics.stale_ms ?? 'n/a'} ms</dd></div>
          </dl>
        </article>

        <article className="card">
          <h2>Session Metrics</h2>
          <dl>
            <div><dt>Lap</dt><dd>{state.metrics.lap_number ?? 'n/a'}</dd></div>
            <div><dt>Laps left</dt><dd>{state.metrics.laps_remaining ?? 'n/a'}</dd></div>
            <div><dt>Fuel</dt><dd>{fmt(state.metrics.fuel_liters)} L</dd></div>
            <div><dt>Last lap</dt><dd>{fmtMs(state.metrics.last_lap_time_ms)}</dd></div>
            <div><dt>Best lap</dt><dd>{fmtMs(state.metrics.best_lap_time_ms)}</dd></div>
          </dl>
        </article>
      </section>

      <section className="card log">
        <h2>Recent Messages</h2>
        <ul>
          {recent.length === 0 ? (
            <li className="empty">No messages yet.</li>
          ) : (
            recent.map((message) => <MessageRow key={message.id} message={message} />)
          )}
        </ul>
      </section>
    </main>
  )
}

function MessageRow({ message }: { message: EngineerMessage }) {
  return (
    <li className={`row ${message.priority}`}>
      <span className="timestamp">{new Date(message.timestamp_ms).toLocaleTimeString()}</span>
      <span className="body">{message.text}</span>
      <span className="tag">{message.category}</span>
    </li>
  )
}

function fmt(value?: number | null) {
  return value == null ? 'n/a' : value.toFixed(1)
}

function fmtMs(value?: number | null) {
  if (value == null) return 'n/a'
  return `${(value / 1000).toFixed(3)}s`
}

