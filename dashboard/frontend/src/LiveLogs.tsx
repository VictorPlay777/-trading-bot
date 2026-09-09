import { useEffect, useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import { getLogs } from './api'
import { Empty, PageHeader, Panel, StatusBadge } from './components'
import { fmtAge, fmtDuration, fmtTs, numberValue } from './format'
import { useLiveStore } from './live'
import type { LogLine } from './types'

const CATEGORIES = ['INFO', 'SUCCESS', 'WARNING', 'ERROR', 'TRADE', 'SYSTEM'] as const
const MAX_RENDERED = 500
const HEARTBEAT_STALE_SEC = 150

function fmtClock(ts: number): string {
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function liveState(status: ReturnType<typeof useLiveStore>['status']) {
  if (!status) return { label: 'OFFLINE', tone: 'danger' as const }
  const stale = status.heartbeat_age_sec == null || status.heartbeat_age_sec > HEARTBEAT_STALE_SEC
  if (!status.process_running) return { label: 'OFFLINE', tone: 'danger' as const }
  if (stale) return { label: 'NO RESPONSE', tone: 'danger' as const }
  if (status.state === 'PAUSED' || status.state === 'KILL_SWITCH') return { label: 'PAUSED', tone: 'warning' as const }
  if (status.state === 'RUNNING') return { label: 'RUNNING', tone: 'success' as const }
  if (status.state === 'EMERGENCY_STOP' || status.state === 'ERROR') return { label: 'ERROR', tone: 'danger' as const }
  return { label: status.state, tone: 'info' as const }
}

export function LiveLogsPage() {
  const { status, logs, connected } = useLiveStore()
  const [history, setHistory] = useState<LogLine[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [category, setCategory] = useState('')
  const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [clearedBefore, setClearedBefore] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)
  const [stuck, setStuck] = useState(true)
  const stickRef = useRef(true)

  useEffect(() => {
    void getLogs('limit=200')
      .then((data) => {
        setHistory(data.items.slice().sort((a, b) => a.id - b.id))
        setHistoryLoaded(true)
      })
      .catch(() => setHistoryLoaded(true))
  }, [])

  const all = useMemo(() => {
    const merged = new Map<number, LogLine>()
    for (const line of history) merged.set(line.id, line)
    for (const line of logs) merged.set(line.id, line)
    return [...merged.values()].sort((a, b) => a.id - b.id).filter((line) => line.id > clearedBefore)
  }, [history, logs, clearedBefore])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return all
      .filter((line) => !category || line.category === category)
      .filter((line) => !needle || line.message.toLowerCase().includes(needle) || (line.symbol ?? '').toLowerCase().includes(needle))
      .slice(-MAX_RENDERED)
  }, [all, category, search])

  const onScroll = () => {
    const el = listRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    stickRef.current = nearBottom
    setStuck(nearBottom)
  }

  useEffect(() => {
    const el = listRef.current
    if (el && autoScroll && stickRef.current) el.scrollTop = el.scrollHeight
  }, [filtered, autoScroll])

  useEffect(() => {
    if (autoScroll && listRef.current) {
      stickRef.current = true
      setStuck(true)
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [autoScroll])

  const download = () => {
    fetch('/api/logs/export?limit=10000', { credentials: 'include', headers: { 'X-Requested-With': 'dashboard' } })
      .then((res) => res.text())
      .then((text) => {
        const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
        const link = document.createElement('a')
        link.href = url
        link.download = `bot_live_logs_${new Date().toISOString().slice(0, 19).replaceAll(':', '-')}.txt`
        link.click()
        URL.revokeObjectURL(url)
      })
      .catch(() => undefined)
  }

  const live = liveState(status)
  const lastActivity = status?.heartbeat_age_sec
  const lastCycleTs = status?.last_heartbeat_ts

  return (
    <>
      <PageHeader eyebrow="MONITORING" title="Live Logs">
        <div className="page-actions">
          <button className={clsx('button tiny', autoScroll ? 'primary' : 'subtle')} onClick={() => setAutoScroll(!autoScroll)}>
            ▼ Auto-scroll {autoScroll ? 'On' : 'Off'}
          </button>
          <button className="button tiny subtle" onClick={() => setClearedBefore(all.length ? all[all.length - 1].id : 0)}>Clear</button>
          <button className="button tiny subtle" onClick={download}>⤓ Download</button>
        </div>
      </PageHeader>

      <div className={clsx('live-status-bar', live.tone)}>
        <div className="live-status-main">
          <span className={clsx('live-dot', live.tone)} />
          <strong>BOT {live.label}</strong>
          <StatusBadge status={status} compact />
        </div>
        <div className="live-status-grid">
          <span>Last activity <b>{lastActivity == null ? '—' : fmtAge(lastActivity)}</b></span>
          <span>Uptime <b>{fmtDuration(status?.uptime_sec)}</b></span>
          <span>Exchange <b className={status?.bybit.connected ? 'profit' : 'loss'}>{status?.bybit.connected ? '● Connected' : '● Disconnected'}</b></span>
          <span>Stream <b className={connected ? 'profit' : 'loss'}>{connected ? '● Connected' : '● Reconnecting'}</b></span>
          <span>Last cycle <b>{lastCycleTs ? `${fmtAge(numberValue(Date.now() / 1000 - lastCycleTs))} (${status?.cycle_ms?.toFixed(0) ?? '—'} ms)` : '—'}</b></span>
          <span>PID <b>{status?.pid ?? '—'}</b></span>
        </div>
        {live.tone === 'danger' && status?.process_running && (
          <div className="alert danger"><strong>No heartbeat</strong><span>Bot process is alive but has not reported activity for {fmtDuration(lastActivity)}. It may be frozen.</span></div>
        )}
      </div>

      <div className="filter-bar">
        <button className={clsx('button tiny', !category && 'selected')} onClick={() => setCategory('')}>All</button>
        {CATEGORIES.map((item) => (
          <button key={item} className={clsx('button tiny', category === item && 'selected')} onClick={() => setCategory(category === item ? '' : item)}>{item}</button>
        ))}
        <input placeholder="Search text or symbol…" value={search} onChange={(event) => setSearch(event.target.value)} />
      </div>

      <Panel title={`${filtered.length} lines${all.length > MAX_RENDERED ? ` (last ${MAX_RENDERED})` : ''}`}>
        {!historyLoaded && filtered.length === 0 && <div className="panel-loading">Loading logs…</div>}
        {historyLoaded && filtered.length === 0 && <Empty text="No log lines yet" />}
        <div className="log-viewer" ref={listRef} onScroll={onScroll}>
          {filtered.map((line) => (
            <div className={clsx('log-line', `cat-${line.category.toLowerCase()}`)} key={line.id}>
              <time>{fmtClock(line.ts)}</time>
              <span className={clsx('level', line.category.toLowerCase())}>{line.category}</span>
              <span className="log-text">{line.symbol && <b>{line.symbol} </b>}{line.message}</span>
            </div>
          ))}
        </div>
        {!stuck && (
          <button className="button tiny primary log-jump" onClick={() => { if (listRef.current) { listRef.current.scrollTop = listRef.current.scrollHeight; stickRef.current = true; setStuck(true); setAutoScroll(true) } }}>↓ Jump to latest</button>
        )}
        <div className="log-footer muted">Live stream + last 200 lines · DB keeps ~20k lines, use Download for archive{all.length ? ` · oldest shown ${fmtTs(filtered[0]?.ts)}` : ''}</div>
      </Panel>
    </>
  )
}
