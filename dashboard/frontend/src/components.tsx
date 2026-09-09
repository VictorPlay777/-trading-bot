import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import clsx from 'clsx'
import { fmtAge, fmtPrice, fmtTs, fmtUsd, toneFor } from './format'
import { useLiveStore } from './live'
import { useLang, LangToggle } from './i18n'
import type { Event, Position, Status } from './types'

const navItems: ReadonlyArray<readonly [string, string, string, string]> = [
  ['/', '▦', 'Dashboard', 'Дашборд'],
  ['/positions', '◈', 'Positions', 'Позиции'],
  ['/strategies', '◎', 'Strategies', 'Стратегии'],
  ['/risk', '◆', 'Risk', 'Риск'],
  ['/statistics', '▥', 'Statistics', 'Статистика'],
  ['/trades', '≋', 'Trades', 'Сделки'],
  ['/logs', '▤', 'Live Logs', 'Логи'],
  ['/research', '⌬', 'Research', 'Исследование'],
  ['/events', '⋮', 'Events', 'События'],
]

export function StatusBadge({ status, compact = false }: { status: Status | string | null; compact?: boolean }) {
  const value = typeof status === 'string' ? status : status?.state
  const label = value?.replaceAll('_', ' ') ?? 'UNKNOWN'
  return (
    <span className={clsx('status-badge', `status-${value?.toLowerCase() ?? 'unknown'}`, compact && 'compact')}>
      <span className="status-dot" />
      {label}
    </span>
  )
}

export function KpiCard({
  label,
  value,
  sub,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'neutral' | 'profit' | 'loss' | 'warning' | 'info'
}) {
  return (
    <article className={clsx('kpi-card', tone)}>
      <span className="eyebrow">{label}</span>
      <strong className="kpi-value tabular">{value}</strong>
      {sub && <span className="kpi-sub">{sub}</span>}
    </article>
  )
}

export function Panel({
  title,
  actions,
  children,
  className,
}: {
  title: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={clsx('panel', className)}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {actions && <div className="panel-actions">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />
}

export function Toasts({ messages, onDismiss }: { messages: string[]; onDismiss: (message: string) => void }) {
  return (
    <div className="toast-stack" aria-live="polite">
      {messages.map((message) => (
        <button className="toast" key={message} onClick={() => onDismiss(message)}>{message}</button>
      ))}
    </div>
  )
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel = 'Confirm',
  danger = false,
  requireText,
  onConfirm,
  onClose,
  children,
}: {
  title: string
  body: ReactNode
  confirmLabel?: string
  danger?: boolean
  requireText?: string
  onConfirm: () => void
  onClose: () => void
  children?: ReactNode
}) {
  const [typed, setTyped] = useState('')
  const valid = !requireText || typed === requireText
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <div className="modal-heading">
          <h2 id="dialog-title">{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Close">×</button>
        </div>
        <p className="modal-body">{body}</p>
        {requireText && (
          <label className="field">
            <span>Type {requireText} to confirm</span>
            <input value={typed} onChange={(event) => setTyped(event.target.value)} autoFocus />
          </label>
        )}
        {children}
        <div className="modal-actions">
          <button className="button subtle" onClick={onClose}>Cancel</button>
          <button className={clsx('button', danger ? 'danger' : 'primary')} disabled={!valid} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

export function PeriodPicker({
  value,
  startDate = '',
  endDate = '',
  onChange,
  onRangeChange,
}: {
  value: string
  startDate?: string
  endDate?: string
  onChange: (value: string) => void
  onRangeChange?: (startDate: string, endDate: string) => void
}) {
  return (
    <div className="period-picker">
      {['today', '7d', '30d', '90d', 'all'].map((period) => (
        <button key={period} className={clsx('button tiny', value === period && 'selected')} onClick={() => onChange(period)}>
          {period === 'today' ? 'Today' : period.toUpperCase()}
        </button>
      ))}
      {value === 'custom' && <span className="date-inputs"><input type="date" value={startDate} onChange={(event) => onRangeChange?.(event.target.value, endDate)} /><input type="date" value={endDate} onChange={(event) => onRangeChange?.(startDate, event.target.value)} /></span>}
      <button className={clsx('button tiny', value === 'custom' && 'selected')} onClick={() => onChange('custom')}>Custom</button>
    </div>
  )
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  renderCard,
}: {
  columns: Array<{ key: string; label: string; render: (row: T) => ReactNode; className?: string }>
  rows: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
  renderCard: (row: T) => ReactNode
}) {
  if (!rows.length) return <Empty text="No data yet" />
  return (
    <>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr>{columns.map((column) => <th className={column.className} key={column.key}>{column.label}</th>)}</tr></thead>
          <tbody>{rows.map((row) => <tr className={onRowClick ? 'clickable' : ''} key={rowKey(row)} onClick={() => onRowClick?.(row)}>{columns.map((column) => <td className={column.className} key={column.key}>{column.render(row)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <div className="mobile-cards">{rows.map((row) => <article className="mobile-card" key={rowKey(row)} onClick={() => onRowClick?.(row)}>{renderCard(row)}</article>)}</div>
    </>
  )
}

export function Layout({ children, onLogout }: { children: ReactNode; onLogout: () => void }) {
  const { status, summaryLight, connected } = useLiveStore()
  const { lang, t } = useLang()
  const [disconnectedFor, setDisconnectedFor] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setDisconnectedFor((value) => connected ? 0 : value + 1000), 1000)
    return () => window.clearInterval(timer)
  }, [connected])
  return (
    <div className="app-shell">
      {!connected && disconnectedFor > 10000 && <div className="lost-banner">{t('Live connection lost · polling status every 5s', 'Соединение потеряно · опрос статуса каждые 5с')}</div>}
      <aside className="sidebar">
        <Link to="/" className="brand"><span className="brand-mark">B</span><span>Bybit Bot Panel</span></Link>
        <nav>{navItems.map(([path, icon, label, ru]) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => clsx('nav-link', isActive && 'active')}><span>{icon}</span>{lang === 'ru' ? ru : label}</NavLink>)}</nav>
        <div className="sidebar-footer"><span className={clsx('connection-dot', connected && 'on')} /> SSE {connected ? t('connected', 'подключено') : t('reconnecting', 'переподключение')}</div>
      </aside>
      <main className="main">
        <header className="top-header">
          <div className="mobile-brand"><span className="brand-mark">B</span> Bot Panel</div>
          <div className="header-status"><StatusBadge status={status} compact /><span className={clsx('bybit-dot', status?.bybit.connected && 'on')} /> <span className="header-hide-mobile">{status?.bybit.connected ? 'Bybit OK' : t('Bybit unavailable', 'Bybit недоступен')}</span></div>
          <div className="header-metrics" title={!status?.bybit.connected ? t('Bybit unavailable', 'Bybit недоступен') : undefined}><span className="tabular">{status?.bybit.connected ? fmtUsd(summaryLight?.equity) : '—'}</span><span className={toneFor(summaryLight?.unrealized)}>{status?.bybit.connected ? fmtUsd(summaryLight?.unrealized) : '—'}</span></div>
          <LangToggle />
          <button className="button tiny subtle" onClick={onLogout}>{t('Logout', 'Выход')}</button>
        </header>
        <div className="page-content">{children}</div>
      </main>
      <nav className="bottom-nav">{navItems.slice(0, 5).map(([path, icon, label, ru]) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => clsx('bottom-link', isActive && 'active')}><span>{icon}</span><small>{lang === 'ru' ? ru : label}</small></NavLink>)}</nav>
    </div>
  )
}

export function PageHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return <div className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1></div>{children && <div className="page-actions">{children}</div>}</div>
}

export function ErrorState({ message }: { message: string }) {
  return <div className="error-state"><strong>Could not load this view</strong><span>{message}</span></div>
}

export function PositionTableCard({ position }: { position: Position }) {
  return <><div className="card-line"><strong>{position.symbol}</strong><span className={position.side === 'long' ? 'profit' : 'loss'}>{position.side}</span><span className="muted">{position.source === 'exchange' ? 'exchange view' : 'bot view'}</span></div><div className="card-grid"><span>Entry <b>{fmtPrice(position.entry_price)}</b></span><span>Mark <b>{fmtPrice(position.mark_price)}</b></span><span>Size <b>{position.qty}</b></span><span>Unrealized <b className={toneFor(position.unrealized_pnl)}>{fmtUsd(position.unrealized_pnl)}</b></span></div></>
}

export function PositionsTable({ positions, onSelect }: { positions: Position[]; onSelect: (position: Position) => void }) {
  return <DataTable
    rows={positions}
    rowKey={(row) => `${row.symbol}-${row.side}`}
    onRowClick={onSelect}
    renderCard={(row) => <PositionTableCard position={row} />}
    columns={[
      { key: 'symbol', label: 'Symbol', render: (row) => <strong>{row.symbol}</strong> },
      { key: 'side', label: 'Side', render: (row) => <span className={clsx('side-chip', row.side === 'long' ? 'long' : 'short')}>{row.side}</span> },
      { key: 'entry', label: 'Entry', render: (row) => <span className="tabular">{fmtPrice(row.entry_price)}</span> },
      { key: 'mark', label: 'Mark', render: (row) => <span className="tabular">{fmtPrice(row.mark_price)}</span> },
      { key: 'size', label: 'Size', render: (row) => <span className="tabular">{row.qty}</span> },
      { key: 'lev', label: 'Lev', render: (row) => <span className="tabular">{row.leverage ?? '—'}x</span> },
      { key: 'sl', label: 'SL', render: (row) => <span className="tabular">{fmtPrice(row.stop_loss)}</span> },
      { key: 'tp', label: 'TP', render: (row) => <span className="tabular">{fmtPrice(row.tp1)}</span> },
      { key: 'pnl', label: 'Unreal PnL', render: (row) => <span className={toneFor(row.unrealized_pnl)}>{fmtUsd(row.unrealized_pnl)}</span> },
      { key: 'opened', label: 'Opened', render: (row) => <span className="muted">{row.opened_ts ? fmtAge((Date.now() / 1000) - Number(row.opened_ts)) : '—'}</span> },
    ]}
  />
}

export function EventList({ events }: { events: Event[] }) {
  if (!events.length) return <Empty text="No events yet" />
  return <div className="event-list">{events.map((event) => <div className="event-row" key={event.id}><span className={clsx('level', event.level.toLowerCase())}>{event.level}</span><span className="event-type">{event.event_type}</span><span className="event-message">{event.symbol && <b>{event.symbol} </b>}{event.message}</span><time>{fmtTs(event.ts)}</time></div>)}</div>
}
