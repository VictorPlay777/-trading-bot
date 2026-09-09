import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import type { Event, LogLine, Position, Status, SummaryLight } from './types'

interface LiveContextValue {
  status: Status | null
  summaryLight: SummaryLight | null
  positions: Position[]
  events: Event[]
  logs: LogLine[]
  connected: boolean
}

const LiveContext = createContext<LiveContextValue | null>(null)

export function LiveProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [summaryLight, setSummaryLight] = useState<SummaryLight | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [logs, setLogs] = useState<LogLine[]>([])
  const [connected, setConnected] = useState(false)
  const [disconnectedAt, setDisconnectedAt] = useState<number | null>(null)

  useEffect(() => {
    let source: EventSource | null = null
    let reconnectTimer: number | undefined
    let stopped = false
    let backoff = 1000
    let lastEventId = 0
    let lastLogId = 0
    const connect = () => {
      if (stopped) return
      source = new EventSource(`/api/stream?since_id=${lastEventId}&since_log_id=${lastLogId}`)
      source.onopen = () => {
        setConnected(true)
        setDisconnectedAt(null)
        backoff = 1000
      }
      source.onerror = () => {
        setConnected(false)
        setDisconnectedAt((value) => value ?? Date.now())
        source?.close()
        reconnectTimer = window.setTimeout(connect, backoff)
        backoff = Math.min(backoff * 2, 30000)
      }
      source.addEventListener('snapshot', (message) => {
        try {
          const data = JSON.parse(message.data) as {
            status: Status
            summary_light: SummaryLight
            positions: Position[]
          }
          setStatus(data.status)
          setSummaryLight(data.summary_light)
          setPositions(data.positions)
        } catch {
          return
        }
      })
      source.addEventListener('events', (message) => {
        try {
          const incoming = JSON.parse(message.data) as Event[]
          if (incoming.length) {
            lastEventId = Math.max(lastEventId, ...incoming.map((item) => item.id))
            setEvents((existing) => {
              const merged = [...incoming, ...existing]
              return Array.from(new Map(merged.map((item) => [item.id, item])).values())
                .sort((left, right) => right.id - left.id)
                .slice(0, 200)
            })
          }
        } catch {
          return
        }
      })
      source.addEventListener('logs', (message) => {
        try {
          const incoming = JSON.parse(message.data) as LogLine[]
          if (incoming.length) {
            lastLogId = Math.max(lastLogId, ...incoming.map((item) => item.id))
            setLogs((existing) => {
              const merged = [...existing, ...incoming]
              return Array.from(new Map(merged.map((item) => [item.id, item])).values())
                .sort((left, right) => left.id - right.id)
                .slice(-500)
            })
          }
        } catch {
          return
        }
      })
    }
    connect()
    return () => {
      stopped = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      source?.close()
    }
  }, [])

  useEffect(() => {
    if (connected) return
    const interval = window.setInterval(() => {
      if (disconnectedAt && Date.now() - disconnectedAt > 10000) {
        void api<Status>('/api/status')
          .then(setStatus)
          .catch((error: unknown) => {
            if (!(error instanceof ApiError)) return
          })
      }
    }, 5000)
    return () => window.clearInterval(interval)
  }, [connected, disconnectedAt])

  const value = useMemo(
    () => ({
      status,
      summaryLight,
      positions,
      events,
      logs,
      connected,
    }),
    [connected, events, logs, positions, status, summaryLight],
  )
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
}

export function useLiveStore(): LiveContextValue {
  const value = useContext(LiveContext)
  if (!value) throw new Error('useLiveStore must be used inside LiveProvider')
  return value
}
