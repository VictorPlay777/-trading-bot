import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Area, AreaChart } from 'recharts'
import { api, ApiError, getEvents, getPosition, getPositions, getRisk, getStats, getStrategies, getStrategySettings, getSummary, getStatus, getTrade, getTrades } from './api'
import { useToast } from './App'
import { ConfirmDialog, DataTable, Empty, ErrorState, EventList, KpiCard, PageHeader, Panel, PeriodPicker, PositionsTable, StatusBadge } from './components'
import { fmtAge, fmtChartTs, fmtDuration, fmtPct, fmtPrice, fmtQty, fmtTs, fmtUsd, numberValue, periodParams, toneFor } from './format'
import { useLiveStore } from './live'
import { useLang } from './i18n'
import type { Fill, Position, RiskResponse, Strategy, StrategyField, StrategySettings, Summary, Trade } from './types'

function useAction() {
  const toast = useToast()
  const client = useQueryClient()
  return async (path: string, body?: unknown, success = 'Action completed') => {
    try {
      await api(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
      toast(success)
      await client.invalidateQueries()
    } catch (error: unknown) {
      toast(error instanceof ApiError ? error.detail : 'Action failed')
    }
  }
}

function LoadingOrError({ loading, error }: { loading: boolean; error: Error | null }) {
  if (loading) return <div className="panel-loading">Loading…</div>
  if (error) return <ErrorState message={error.message} />
  return null
}

export function Login() {
  const { t } = useLang()
  const navigate = useNavigate()
  const toast = useToast()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      navigate('/', { replace: true })
    } catch (reason: unknown) {
      const detail = reason instanceof ApiError ? reason.detail : 'Login failed'
      setError(detail)
      toast(detail)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={(event) => void submit(event)}>
        <div className="brand large"><span className="brand-mark">B</span><span>Bybit Bot Panel</span></div>
        <span className="eyebrow">SECURE OPERATIONS CONSOLE</span>
        <h1>{t('Welcome back', 'С возвращением')}</h1>
        <p className="muted">{t('Sign in to monitor and control the trading process.', 'Войдите, чтобы наблюдать и управлять ботом.')}</p>
        <label className="field"><span>{t('Username', 'Логин')}</span><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
        <label className="field"><span>{t('Password', 'Пароль')}</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
        {error && <div className="inline-error">{error}</div>}
        <button className="button primary full" disabled={busy}>{busy ? t('Signing in…', 'Вход…') : t('Sign in', 'Войти')}</button>
      </form>
    </div>
  )
}

function DashboardControls({ status }: { status: Summary['status'] }) {
  const { t } = useLang()
  const action = useAction()
  const [dialog, setDialog] = useState<'stop' | 'emergency' | 'reset' | 'kill' | null>(null)
  const [closePositions, setClosePositions] = useState(false)
  const stopped = status.state === 'STOPPED' || status.state === 'ERROR'
  const running = status.process_running
  return (
    <>
      <div className="control-grid">
        <button className="button primary" disabled={!stopped || Boolean(status.control.emergency_stop)} onClick={() => void action('/api/bot/start', undefined, 'Bot start requested')}>▶ {t('Start', 'Старт')}</button>
        <button className="button warning" disabled={!running} onClick={() => void action(status.control.paused ? '/api/bot/resume' : '/api/bot/pause', undefined, status.control.paused ? 'Bot resumed' : 'Bot paused')}>{status.control.paused ? `▶ ${t('Resume', 'Возобновить')}` : `Ⅱ ${t('Pause', 'Пауза')}`}</button>
        <button className="button subtle" disabled={!running} onClick={() => setDialog('stop')}>■ {t('Stop', 'Стоп')}</button>
        <button className="button danger" onClick={() => setDialog('emergency')}>🛑 {t('Emergency stop', 'Аварийный стоп')}</button>
      </div>
      {dialog === 'stop' && <ConfirmDialog title={t('Stop the bot?', 'Остановить бота?')} body={status.managed ? t('The managed bot process will receive SIGTERM.', 'Управляемый процесс бота получит SIGTERM.') : t('An external bot process is running. Allowing external stop will send it SIGTERM.', 'Запущен внешний процесс бота. Остановка отправит ему SIGTERM.')} confirmLabel={t('Stop bot', 'Остановить')} danger onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); void action('/api/bot/stop', { allow_external: !status.managed }, 'Bot stop requested') }} />}
      {dialog === 'emergency' && <ConfirmDialog title={t('Emergency stop', 'Аварийный стоп')} body={t('This disables trading and stops the bot immediately.', 'Торговля отключается, бот останавливается немедленно.')} confirmLabel={t('Emergency stop', 'Аварийный стоп')} danger requireText="EMERGENCY STOP" onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); void action('/api/bot/emergency-stop', { confirm_phrase: 'EMERGENCY STOP', close_positions: closePositions }, 'Emergency stop requested') }}><label className="checkbox-row"><input type="checkbox" checked={closePositions} onChange={(event) => setClosePositions(event.target.checked)} /> {t('Also close all open positions on Bybit', 'Также закрыть все открытые позиции на Bybit')}</label></ConfirmDialog>}
      {dialog === 'reset' && <ConfirmDialog title={t('Reset emergency stop?', 'Сбросить аварийный стоп?')} body={t('Trading will be enabled and the paused state cleared.', 'Торговля будет включена, пауза снята.')} confirmLabel={t('Reset emergency', 'Сбросить')} onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); void action('/api/bot/reset-emergency', { confirm: true }, 'Emergency stop reset') }} />}
      {dialog === 'kill' && <ConfirmDialog title={t('Reset kill switch?', 'Сбросить kill switch?')} body={t('The persisted kill-switch state will be cleared.', 'Сохранённое состояние kill switch будет сброшено.')} confirmLabel={t('Reset kill switch', 'Сбросить kill switch')} onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); void action('/api/bot/kill-switch/reset', { confirm: true }, 'Kill switch reset') }} />}
      <div className="alerts">
        {status.state === 'KILL_SWITCH' && <div className="alert warning"><strong>{t('Kill switch triggered', 'Kill switch сработал')}</strong><span>{status.control.kill_switch_reason ?? status.kill_switch.triggered_reason ?? t('Daily loss limit reached', 'Достигнут дневной лимит убытка')}</span><button className="button tiny" onClick={() => setDialog('kill')}>{t('Reset kill switch', 'Сбросить kill switch')}</button></div>}
        {status.state === 'EMERGENCY_STOP' && <div className="alert danger"><strong>{t('Emergency stop active', 'Аварийный стоп активен')}</strong><span>{t('Trading is disabled until manually reset.', 'Торговля отключена до ручного сброса.')}</span><button className="button tiny danger" onClick={() => setDialog('reset')}>{t('Reset emergency', 'Сбросить')}</button></div>}
      </div>
    </>
  )
}

export function Dashboard() {
  const { t } = useLang()
  const { status: liveStatus, summaryLight, events } = useLiveStore()
  const summaryQuery = useQuery({ queryKey: ['summary'], queryFn: getSummary, refetchInterval: 10000 })
  const summary = summaryQuery.data
  const status = liveStatus ?? summary?.status ?? null
  const light = summaryLight
  if (!summary && summaryQuery.isPending) return <div className="panel-loading">Loading dashboard…</div>
  if (!summary || !status) return <ErrorState message={summaryQuery.error?.message ?? 'No dashboard snapshot yet'} />
  const equity = light?.equity ?? summary.wallet.equity
  const unrealized = light?.unrealized ?? summary.wallet.unrealized_pnl
  const dailyLoss = numberValue(summary.kill_switch.day_start_equity) - numberValue(equity)
  const dailyLossPct = numberValue(summary.kill_switch.day_start_equity) ? dailyLoss / numberValue(summary.kill_switch.day_start_equity) * 100 : 0
  return (
    <>
      <PageHeader eyebrow={t('OPERATIONS', 'УПРАВЛЕНИЕ')} title={t('Dashboard', 'Дашборд')}>
        <div className="header-summary"><StatusBadge status={status} /><span className={clsx('chip', status.bybit.connected ? 'success' : 'danger')}>{status.bybit.connected ? '● Bybit OK' : `● ${t('CONNECTION ERROR', 'ОШИБКА СОЕДИНЕНИЯ')}`}</span><span className="chip">{t('Heartbeat', 'Хартбит')} {status.state === 'STOPPED' ? '—' : fmtAge(status.heartbeat_age_sec)}</span><span className="chip">{t('Uptime', 'Аптайм')} {status.state === 'STOPPED' ? '—' : fmtDuration(status.uptime_sec)}</span>{status.strategy_id && <span className="chip">{status.strategy_id}</span>}</div>
      </PageHeader>
      <div className="warning-pills">{status.warnings.map((warning) => <span className="pill warning" key={warning}>{warning}</span>)}</div>
      <DashboardControls status={status} />
      <div className="kpi-grid">
        <KpiCard label={t('Balance', 'Баланс')} value={fmtUsd(summary.wallet.wallet_balance)} />
        <KpiCard label={t('Equity', 'Эквити')} value={fmtUsd(equity)} tone={toneFor(equity) === 'profit' ? 'profit' : 'neutral'} />
        <KpiCard label={t('Available', 'Доступно')} value={fmtUsd(summary.wallet.available_balance)} />
        <KpiCard label={t('Unrealized PnL', 'Нереализ. PnL')} value={fmtUsd(unrealized)} tone={toneFor(unrealized) === 'profit' ? 'profit' : toneFor(unrealized) === 'loss' ? 'loss' : 'neutral'} />
        <KpiCard label={t('Realized PnL', 'Реализ. PnL')} value={fmtUsd(summary.realized_pnl_all)} tone={toneFor(summary.realized_pnl_all) === 'profit' ? 'profit' : 'loss'} />
        <KpiCard label={t('PnL Today', 'PnL сегодня')} value={fmtUsd(light?.pnl_today ?? summary.pnl_today)} tone={toneFor(light?.pnl_today ?? summary.pnl_today) === 'profit' ? 'profit' : 'loss'} />
        <KpiCard label="PnL 7D" value={fmtUsd(summary.pnl_7d)} tone={toneFor(summary.pnl_7d) === 'profit' ? 'profit' : 'loss'} />
        <KpiCard label="PnL 30D" value={fmtUsd(summary.pnl_30d)} tone={toneFor(summary.pnl_30d) === 'profit' ? 'profit' : 'loss'} />
        <KpiCard label={t('Drawdown', 'Просадка')} value={fmtUsd(summary.drawdown.usd, false)} sub={summary.drawdown_source === 'equity_snapshots' ? `${summary.drawdown.pct == null ? '—' : fmtPct(summary.drawdown.pct)} ${t('from 90d equity peak', 'от пика эквити за 90д')}` : summary.drawdown_source === 'trades' ? t('from cumulative PnL peak (no equity history)', 'от пика накопл. PnL (нет истории эквити)') : t('no equity history yet', 'истории эквити пока нет')} tone="loss" />
        <KpiCard label={t('Open positions', 'Открытые позиции')} value={light?.open_positions ?? summary.open_positions} />
        <KpiCard label={t('Trades today', 'Сделок сегодня')} value={summary.trades_today} />
        <KpiCard label={t('Daily loss', 'Дневной убыток')} value={`${fmtUsd(-dailyLoss)} (${fmtPct(-dailyLossPct)})`} sub={`${t('limit', 'лимит')} ${fmtPct(summary.risk.max_daily_loss_pct)}`} tone={dailyLoss < 0 ? 'warning' : 'neutral'} />
      </div>
      <div className="two-column">
        <Panel title={t('Recent events', 'Последние события')}><EventList events={events.slice(0, 15)} /></Panel>
        <Panel title={t('Connection details', 'Детали соединения')}><div className="detail-list"><div><span>{t('Process', 'Процесс')}</span><strong>{status.process_running ? `PID ${status.pid ?? '—'}` : t('Stopped', 'Остановлен')}</strong></div><div><span>{t('Heartbeat', 'Хартбит')}</span><strong>{fmtAge(status.heartbeat_age_sec)}</strong></div><div><span>{t('Cycle', 'Цикл')}</span><strong>{status.cycle_ms ? `${status.cycle_ms.toFixed(0)} ms` : '—'}</strong></div><div><span>{t('Last exit', 'Посл. выход')}</span><strong>{status.last_exit_code ?? '—'}</strong></div><div><span>{t('Trading enabled', 'Торговля вкл.')}</span><strong>{status.control.trading_enabled ? t('Yes', 'Да') : t('No', 'Нет')}</strong></div></div></Panel>
      </div>
    </>
  )
}

export function PositionsPage() {
  const { t } = useLang()
  const { positions: livePositions } = useLiveStore()
  const positionsQuery = useQuery({ queryKey: ['positions'], queryFn: getPositions, refetchInterval: 10000 })
  const [selected, setSelected] = useState<Position | null>(null)
  const positions = livePositions.length ? livePositions : positionsQuery.data ?? []
  return (
    <>
      <PageHeader eyebrow={t('RISK EXPOSURE','РИСК')} title={t('Positions','Позиции')}><span className="chip">{positions.length} open</span></PageHeader>
      <Panel title="Open positions"><LoadingOrError loading={positionsQuery.isPending && !positions.length} error={positionsQuery.error} /><PositionsTable positions={positions} onSelect={setSelected} /></Panel>
      {selected && <PositionDrawer position={selected} onClose={() => setSelected(null)} />}
    </>
  )
}

function PositionDrawer({ position, onClose }: { position: Position; onClose: () => void }) {
  const detail = useQuery({ queryKey: ['position', position.symbol], queryFn: () => getPosition(position.symbol) })
  const action = useAction()
  const toast = useToast()
  const [dialog, setDialog] = useState<'close' | 'cancel' | null>(null)
  const [sltp, setSltp] = useState({ stop_loss: position.stop_loss ?? '', tp1: position.tp1 ?? '', tp2: position.tp2 ?? '', tp3: position.tp3 ?? '' })
  const data = detail.data
  const mark = numberValue(data?.mark_price ?? position.mark_price)
  const valid = position.side === 'long'
    ? (!sltp.stop_loss || numberValue(sltp.stop_loss) < mark) && (!sltp.tp1 || numberValue(sltp.tp1) > mark)
    : (!sltp.stop_loss || numberValue(sltp.stop_loss) > mark) && (!sltp.tp1 || numberValue(sltp.tp1) < mark)
  const save = async () => {
    try {
      await api(`/api/positions/${position.symbol}/sltp`, { method: 'POST', body: JSON.stringify(Object.fromEntries(Object.entries(sltp).map(([key, value]) => [key, value === '' ? null : Number(value)]))) })
      toast('SL/TP override saved')
    } catch (error: unknown) {
      toast(error instanceof ApiError ? error.detail : 'SL/TP update failed')
    }
  }
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><aside className="drawer"><div className="drawer-heading"><div><span className="eyebrow">POSITION DETAIL</span><h2>{position.symbol}</h2></div><button className="icon-button" onClick={onClose}>×</button></div><LoadingOrError loading={detail.isPending} error={detail.error} />{data && <><div className="drawer-hero"><span className={clsx('side-chip', data.side === 'long' ? 'long' : 'short')}>{data.side}</span><strong className={toneFor(data.unrealized_pnl)}>{fmtUsd(data.unrealized_pnl)}</strong><span className="chip">{data.source === 'exchange' ? 'exchange view (bot heartbeat stale)' : 'bot view'}</span></div><div className="detail-grid"><div>Entry <strong>{fmtPrice(data.entry_price)}</strong></div><div>Mark <strong>{fmtPrice(data.mark_price)}</strong></div><div>Qty <strong>{data.qty}</strong></div><div>Notional <strong>{fmtUsd(data.notional)}</strong></div><div>Leverage <strong>{data.leverage ?? '—'}x</strong></div><div>R multiple <strong>{data.r_multiple == null ? '—' : numberValue(data.r_multiple).toFixed(2)}</strong></div><div>Stop loss <strong>{fmtPrice(data.stop_loss)}</strong></div><div>TP1 / TP2 / TP3 <strong>{fmtPrice(data.tp1)} / {fmtPrice(data.tp2)} / {fmtPrice(data.tp3)}</strong></div><div>Trailing price <strong>{fmtPrice(data.trailing_price)}</strong></div><div>Strategy <strong>{data.strategy_id ?? '—'}</strong></div></div><div className="drawer-actions"><button className="button danger" onClick={() => setDialog('close')}>Close position</button><button className="button subtle" onClick={() => setDialog('cancel')}>Cancel orders</button></div><Panel title="Edit SL / TP"><div className="form-grid">{(['stop_loss', 'tp1', 'tp2', 'tp3'] as const).map((key) => <label className="field" key={key}><span>{key.replace('_', ' ').toUpperCase()}</span><input type="number" value={sltp[key]} onChange={(event) => setSltp({ ...sltp, [key]: event.target.value })} /></label>)}</div><button className="button primary" disabled={!valid} onClick={() => void save()}>Save override</button>{!valid && <small className="inline-error">Long positions require SL &lt; mark &lt; TP; short positions invert this relation.</small>}</Panel><Panel title="Open orders"><DataTable rows={data.open_orders} rowKey={(row) => String(row.orderId ?? row.order_id ?? row.id ?? JSON.stringify(row))} renderCard={(row) => <div className="card-grid"><span>Side <b>{String(row.side ?? '—')}</b></span><span>Qty <b>{String(row.qty ?? row.orderQty ?? '—')}</b></span><span>Price <b>{String(row.price ?? row.orderPrice ?? '—')}</b></span><span>Status <b>{String(row.orderStatus ?? row.status ?? '—')}</b></span></div>} columns={[{ key: 'id', label: 'Order', render: (row) => String(row.orderId ?? row.order_id ?? '—') }, { key: 'side', label: 'Side', render: (row) => String(row.side ?? '—') }, { key: 'type', label: 'Type', render: (row) => String(row.orderType ?? row.type ?? '—') }, { key: 'qty', label: 'Qty', render: (row) => String(row.qty ?? row.orderQty ?? '—') }, { key: 'price', label: 'Price', render: (row) => fmtPrice(row.price ?? row.orderPrice) }, { key: 'status', label: 'Status', render: (row) => String(row.orderStatus ?? row.status ?? '—') }]} /></Panel><Panel title="Recent fills"><DataTable rows={data.fills} rowKey={(row) => String(row.order_id ?? row.timestamp ?? row.ts ?? `${row.symbol}-${row.price}-${row.qty}`)} renderCard={(row) => <div className="card-grid"><span>Side <b>{row.side ?? '—'}</b></span><span>Qty <b>{row.qty ?? '—'}</b></span><span>Price <b>{fmtPrice(row.price)}</b></span><span>Fee <b>{fmtUsd(row.fee)}</b></span></div>} columns={[{ key: 'time', label: 'Time', render: (row) => fmtTs(row.timestamp ?? row.ts) }, { key: 'side', label: 'Side', render: (row) => row.side ?? '—' }, { key: 'qty', label: 'Qty', render: (row) => row.qty ?? '—' }, { key: 'price', label: 'Price', render: (row) => fmtPrice(row.price) }, { key: 'fee', label: 'Fee', render: (row) => fmtUsd(row.fee) }]} /></Panel><Panel title="Recent events"><EventList events={data.events} /></Panel></>}{dialog === 'close' && <ConfirmDialog title="Close position?" body={`Market reduce-only order for ${position.symbol}.`} confirmLabel="Close position" danger onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); void action(`/api/positions/${position.symbol}/close`, { confirm: true }, 'Position close requested') }} />}{dialog === 'cancel' && <ConfirmDialog title="Cancel open orders?" body={`Cancel all open orders for ${position.symbol}.`} confirmLabel="Cancel orders" danger onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); void action(`/api/positions/${position.symbol}/cancel-orders`, { confirm: true }, 'Orders cancellation requested') }} />}</aside></div>
}

export function StrategiesPage() {
  const { t } = useLang()
  const query = useQuery({ queryKey: ['strategies'], queryFn: getStrategies })
  const action = useAction()
  const [confirm, setConfirm] = useState<Strategy | null>(null)
  return <><PageHeader eyebrow={t('CONFIGURATION','КОНФИГУРАЦИЯ')} title={t('Strategies','Стратегии')} /><LoadingOrError loading={query.isPending} error={query.error} /><div className="strategy-grid">{(query.data ?? []).map((strategy) => <article className="strategy-card" key={strategy.strategy_id}><div className="strategy-heading"><div><span className="eyebrow">STRATEGY</span><h2>{strategy.strategy_id}</h2></div><span className={clsx('pill', strategy.enabled ? 'success' : 'muted')}>{strategy.enabled ? 'Active' : 'Inactive'}</span></div><div className="strategy-status"><StatusBadge status={strategy.running ? 'RUNNING' : 'STOPPED'} compact /><span>{strategy.running ? 'running' : 'idle'}</span></div><div className="metric-grid"><span>Trades <b>{strategy.trades ?? 0}</b></span><span>Win rate <b>{fmtPct(strategy.win_rate)}</b></span><span>PF <b>{numberValue(strategy.profit_factor).toFixed(2)}</b></span><span>PnL <b className={toneFor(strategy.pnl)}>{fmtUsd(strategy.pnl)}</b></span><span>Avg R <b>{strategy.avg_r == null ? '—' : numberValue(strategy.avg_r).toFixed(2)}</b></span><span>Max DD <b>{fmtUsd(strategy.max_drawdown, false)}{strategy.max_drawdown_pct == null ? '' : ` / ${fmtPct(strategy.max_drawdown_pct)}`}</b></span><span>Today <b>{strategy.trades_today}</b></span><span>Open <b>{strategy.open_positions}</b></span></div><div className="card-actions"><button className="button subtle" onClick={() => setConfirm(strategy)}>{strategy.enabled ? 'Disable' : 'Enable'}</button>{strategy.active && <Link className="button primary" to={`/strategies/${strategy.strategy_id}/settings`}>Settings</Link>}</div></article>)}</div>{confirm && <ConfirmDialog title={`${confirm.enabled ? 'Disable' : 'Enable'} strategy?`} body={`${confirm.strategy_id} will ${confirm.enabled ? 'stop opening new trades' : 'be enabled for trading'}.`} confirmLabel={confirm.enabled ? 'Disable' : 'Enable'} danger={confirm.enabled} onClose={() => setConfirm(null)} onConfirm={() => { const path = `/api/strategies/${confirm.strategy_id}/${confirm.enabled ? 'disable' : 'enable'}`; setConfirm(null); void action(path, undefined, `Strategy ${confirm.enabled ? 'disabled' : 'enabled'}`) }} />}</>
}

function SettingsForm({ data }: { data: StrategySettings }) {
  const action = useAction()
  const client = useQueryClient()
  const toast = useToast()
  const [values, setValues] = useState<Record<string, boolean | number | string>>(() => Object.fromEntries(data.fields.map((field) => [field.name, field.current])))
  const [restart, setRestart] = useState(false)
  const [confirm, setConfirm] = useState<'save' | 'clear' | null>(null)
  const changed = data.fields.filter((field) => values[field.name] !== field.current)
  const setValue = (field: StrategyField, raw: string | boolean) => setValues({ ...values, [field.name]: field.type === 'bool' ? raw === true : field.type === 'int' || field.type === 'float' ? Number(raw) : raw })
  return <><div className="settings-groups">{(['dangerous', 'other'] as const).map((group) => <div key={group}><h3 className={group === 'dangerous' ? 'danger-heading' : ''}>{group === 'dangerous' ? 'Dangerous' : 'Other'}</h3>{data.fields.filter((field) => group === 'dangerous' ? field.dangerous : !field.dangerous).map((field) => <div className="setting-row" key={field.name}><div><strong>{field.name}</strong><small>{field.type} · default {String(field.default)}</small></div><div className="setting-control">{field.type === 'bool' ? <input type="checkbox" checked={Boolean(values[field.name])} onChange={(event) => setValue(field, event.target.checked)} /> : <input type={field.type === 'str' ? 'text' : 'number'} step={field.type === 'float' ? 'any' : '1'} value={String(values[field.name])} onChange={(event) => setValue(field, event.target.value)} />} {field.override && <span className="pill info">overridden</span>} {field.override && <button className="link-button" onClick={() => setValues({ ...values, [field.name]: field.default })}>reset</button>}</div></div>)}</div>)}</div><div className="settings-footer"><span>{changed.length ? `Unsaved changes (${changed.length})` : 'All changes saved'}</span><div><button className="button subtle" disabled={!changed.length} onClick={() => setValues(Object.fromEntries(data.fields.map((field) => [field.name, field.current])))}>Discard</button><button className="button subtle" disabled={!data.fields.some((field) => field.override)} onClick={() => setConfirm('clear')}>Clear all overrides</button><button className="button primary" disabled={!changed.length} onClick={() => setConfirm('save')}>Save</button></div></div>{confirm === 'save' && <ConfirmDialog title="Save strategy settings?" body={<div>{changed.map((field) => <div className={field.dangerous ? 'danger-text' : ''} key={field.name}><b>{field.name}</b>: {String(field.current)} → {String(values[field.name])}</div>)}</div>} confirmLabel="Save settings" danger={changed.some((field) => field.dangerous)} onClose={() => setConfirm(null)} onConfirm={() => { setConfirm(null); void action(`/api/strategies/${data.strategy_id}/settings`, { overrides: Object.fromEntries(changed.map((field) => [field.name, values[field.name]])), restart }, 'Strategy settings saved') }}><label className="checkbox-row"><input type="checkbox" checked={restart} onChange={(event) => setRestart(event.target.checked)} /> Restart bot now to apply</label></ConfirmDialog>}{confirm === 'clear' && <ConfirmDialog title="Clear all overrides?" body="Every persisted override for this strategy will be removed and defaults will apply on the next restart." confirmLabel="Clear overrides" danger onClose={() => setConfirm(null)} onConfirm={() => { setConfirm(null); void api(`/api/strategies/${data.strategy_id}/settings`, { method: 'DELETE' }).then(async () => { toast('All strategy overrides cleared'); await client.invalidateQueries({ queryKey: ['strategy-settings', data.strategy_id] }) }).catch((error: unknown) => toast(error instanceof ApiError ? error.detail : 'Could not clear overrides')) }} />}
  </>
}

export function StrategySettingsPage() {
  const { t } = useLang()
  const { strategyId = '' } = useParams()
  const query = useQuery({ queryKey: ['strategy-settings', strategyId], queryFn: () => getStrategySettings(strategyId) })
  return <><PageHeader eyebrow={t('STRATEGY SETTINGS','НАСТРОЙКИ СТРАТЕГИИ')} title={strategyId}><Link className="button subtle" to="/strategies">← Back</Link></PageHeader><div className="alert info">Settings apply on bot restart ({query.data?.applies_on ?? 'restart'}).</div>{query.data && <SettingsForm data={query.data} />}{query.isPending && <div className="panel-loading">Loading settings…</div>}{query.error && <ErrorState message={query.error.message} />}</>
}

function RiskField({ field, value, onChange }: { field: { key: string; type: string; label: string; min: number; max: number | null }; value: unknown; onChange: (value: unknown) => void }) {
  if (field.key === 'allowed_symbols') return <label className="field wide"><span>{field.label}</span><input value={Array.isArray(value) ? value.join(', ') : ''} onChange={(event) => onChange(event.target.value.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean))} placeholder="BTCUSDT, ETHUSDT" /><small>Empty means all symbols</small></label>
  if (typeof value === 'boolean') return <label className="checkbox-row"><input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} /> {field.label}</label>
  return <label className="field"><span>{field.label}</span><input type="number" min={field.min} max={field.max ?? undefined} value={String(value ?? '')} onChange={(event) => onChange(Number(event.target.value))} /></label>
}

export function RiskPage() {
  const { t } = useLang()
  const query = useQuery({ queryKey: ['risk'], queryFn: getRisk })
  const controlQuery = useQuery({ queryKey: ['control'], queryFn: () => api<{ trading_enabled: boolean }>('/api/control') })
  const statusQuery = useQuery({ queryKey: ['status'], queryFn: getStatus })
  const action = useAction()
  const toast = useToast()
  const client = useQueryClient()
  const [values, setValues] = useState<RiskResponse | null>(null)
  const [confirm, setConfirm] = useState(false)
  useEffect(() => { if (query.data && !values) setValues(query.data) }, [query.data, values])
  if (query.isPending || !values) return <div className="panel-loading">Loading risk settings…</div>
  if (query.error) return <ErrorState message={query.error.message} />
  const schema = [...values.schema, { key: 'long_enabled', type: 'bool', label: 'Long enabled', min: 0, max: null, dangerous: false }, { key: 'short_enabled', type: 'bool', label: 'Short enabled', min: 0, max: null, dangerous: false }, { key: 'allowed_symbols', type: 'symbols', label: 'Allowed symbols', min: 0, max: null, dangerous: false }, { key: 'kill_switch_enabled', type: 'bool', label: 'Kill switch enabled', min: 0, max: null, dangerous: true }, { key: 'kill_switch_close_positions', type: 'bool', label: 'Kill switch closes positions', min: 0, max: null, dangerous: true }, { key: 'kill_switch_auto_reset_daily', type: 'bool', label: 'Auto-reset kill switch daily', min: 0, max: null, dangerous: false }]
  const changed = schema.some((field) => JSON.stringify(values[field.key as keyof RiskResponse]) !== JSON.stringify(query.data[field.key as keyof RiskResponse]))
  return <><PageHeader eyebrow={t('RISK CONTROLS','УПРАВЛЕНИЕ РИСКОМ')} title={t('Risk','Риск')}><span className="chip">0 = no limit</span></PageHeader><div className="two-column"><Panel title="Risk limits"><div className="form-grid">{schema.map((field) => <RiskField key={field.key} field={field} value={values[field.key as keyof RiskResponse]} onChange={(value) => setValues({ ...values, [field.key]: value })} />)}</div><div className="settings-footer inline"><span>{changed ? 'Unsaved changes' : 'All changes saved'}</span><button className="button primary" disabled={!changed} onClick={() => setConfirm(true)}>Save risk settings</button></div></Panel><div><Panel title="Trading enabled"><div className="toggle-card"><strong>{controlQuery.data?.trading_enabled ? 'Trading is enabled' : 'Trading is disabled'}</strong><button className={clsx('toggle', controlQuery.data?.trading_enabled && 'on')} onClick={() => void action('/api/control', { trading_enabled: !controlQuery.data?.trading_enabled }, 'Trading control updated')}><span /></button></div></Panel><Panel title="Kill switch status"><div className="detail-list"><div><span>Today's start equity</span><strong>{fmtUsd(statusQuery.data?.kill_switch?.day_start_equity)}</strong></div><div><span>Current equity</span><strong>{fmtUsd(statusQuery.data?.kill_switch?.current_equity)}</strong></div><div><span>Triggered</span><strong>{statusQuery.data?.kill_switch?.triggered ? 'Yes' : 'No'}</strong></div><div><span>Reason</span><strong>{statusQuery.data?.kill_switch?.triggered_reason ?? '—'}</strong></div></div><p className="muted note">Kill-switch position closing is not implemented automatically by the bot; it is used by Emergency Stop defaults.</p></Panel></div></div>{confirm && <ConfirmDialog title="Save risk settings?" body="These settings affect position sizing and safety limits." confirmLabel="Save risk" danger onClose={() => setConfirm(false)} onConfirm={() => { setConfirm(false); void api<RiskResponse>('/api/risk', { method: 'PUT', body: JSON.stringify(Object.fromEntries(schema.map((field) => [field.key, values[field.key as keyof RiskResponse]]))) }).then((updated) => { setValues(updated); toast('Risk settings saved'); return client.invalidateQueries({ queryKey: ['risk'] }) }).catch((error: unknown) => toast(error instanceof ApiError ? error.detail : 'Risk update failed')) }} />}</>
}

export function StatisticsPage() {
  const { t } = useLang()
  const [period, setPeriod] = useState('30d')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const params = periodParams(period, startDate, endDate)
  const query = useQuery({ queryKey: ['stats', params], queryFn: () => getStats(new URLSearchParams(params).toString()) })
  const data = query.data
  return <><PageHeader eyebrow={t('PERFORMANCE','РЕЗУЛЬТАТЫ')} title={t('Statistics','Статистика')}><PeriodPicker value={period} startDate={startDate} endDate={endDate} onChange={setPeriod} onRangeChange={(start, end) => { setStartDate(start); setEndDate(end) }} /></PageHeader>{query.isPending && <div className="panel-loading">Loading statistics…</div>}{query.error && <ErrorState message={query.error.message} />}{data && <><div className="metric-grid stats-grid">{[['Total trades', data.metrics.total_trades], ['Win rate', fmtPct(data.metrics.win_rate)], ['Profit factor', numberValue(data.metrics.profit_factor).toFixed(2)], ['Expectancy', fmtUsd(data.metrics.expectancy)], ['Avg win', fmtUsd(data.metrics.avg_win)], ['Avg loss', fmtUsd(data.metrics.avg_loss)], ['Avg R', numberValue(data.metrics.avg_r).toFixed(2)], ['Max DD', `${fmtUsd(data.metrics.max_drawdown_usd, false)}${data.metrics.max_drawdown_pct == null ? '' : ` / ${fmtPct(data.metrics.max_drawdown_pct)}`}`], ['Sharpe', data.metrics.sharpe == null ? `n/a · ${data.metrics.sharpe_note ?? ''}` : numberValue(data.metrics.sharpe).toFixed(2)], ['Long WR', fmtPct(data.metrics.long_win_rate)], ['Short WR', fmtPct(data.metrics.short_win_rate)], ['Total PnL', fmtUsd(data.metrics.total_pnl)], ['Fees', `${fmtUsd(data.metrics.total_fees, false)} (${data.metrics.fees_source})`]].map(([label, value]) => <div className="metric-tile" key={String(label)}><span>{label}</span><b>{String(value)}</b></div>)}</div><div className="chart-grid"><ChartPanel title="Equity curve" data={data.equity_curve} dataKey="equity" color="#38bdf8" empty="No equity snapshots yet — collected since dashboard bridge started" /><ChartPanel title="Cumulative PnL" data={data.cumulative_pnl} dataKey="cum_pnl" color="#4ade80" /><ChartPanel title="Daily PnL" data={data.daily_pnl} dataKey="pnl" color="#f59e0b" bar /><ChartPanel title="Drawdown" data={data.drawdown} dataKey="dd" color="#f87171" area /><ChartPanel title="Trades per day" data={data.trades_per_day} dataKey="trades" color="#38bdf8" bar /></div><Panel title="By strategy"><DataTable rows={Object.entries(data.by_strategy).map(([strategy_id, values]) => ({ strategy_id, values }))} rowKey={(row) => row.strategy_id} renderCard={(row) => <><strong>{row.strategy_id}</strong><div className="card-grid"><span>Trades <b>{row.values.trades}</b></span><span>PnL <b className={toneFor(row.values.pnl)}>{fmtUsd(row.values.pnl)}</b></span><span>Max DD <b>{fmtUsd(row.values.max_drawdown, false)}</b></span></div></>} columns={[{ key: 'strategy', label: 'Strategy', render: (row) => row.strategy_id }, { key: 'trades', label: 'Trades', render: (row) => row.values.trades }, { key: 'win', label: 'Win rate', render: (row) => fmtPct(row.values.win_rate) }, { key: 'pnl', label: 'PnL', render: (row) => fmtUsd(row.values.pnl) }, { key: 'max-dd', label: 'Max DD', render: (row) => fmtUsd(row.values.max_drawdown, false) }, { key: 'avg-r', label: 'Avg R', render: (row) => row.values.avg_r == null ? '—' : numberValue(row.values.avg_r).toFixed(2) }, { key: 'last-trade', label: 'Last trade', render: (row) => fmtTs(row.values.last_trade_ts) }, { key: 'pf', label: 'PF', render: (row) => numberValue(row.values.profit_factor).toFixed(2) }]} /></Panel><ul className="notes">{data.notes.map((note) => <li key={note}>{note}</li>)}</ul></>}</>
}

function ChartPanel({ title, data, dataKey, color, bar = false, area = false, empty }: { title: string; data: Array<Record<string, unknown>>; dataKey: string; color: string; bar?: boolean; area?: boolean; empty?: string }) {
  return <Panel title={title}>{data.length ? <div className="chart"><ResponsiveContainer width="100%" height={260}>{bar ? <BarChart data={data}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey={data[0]?.date !== undefined ? 'date' : 'ts'} tickFormatter={fmtChartTs} stroke="#64748b" /><YAxis stroke="#64748b" /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]}>{data.map((row, index) => <Cell key={index} fill={dataKey === 'pnl' ? (numberValue(row[dataKey]) >= 0 ? '#4ade80' : '#f87171') : color} />)}</Bar></BarChart> : area ? <AreaChart data={data}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="ts" tickFormatter={fmtChartTs} stroke="#64748b" /><YAxis stroke="#64748b" /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Area dataKey={dataKey} stroke={color} fill={`${color}33`} /></AreaChart> : <LineChart data={data}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="ts" tickFormatter={fmtChartTs} stroke="#64748b" /><YAxis stroke="#64748b" /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={2} /></LineChart>}</ResponsiveContainer></div> : <Empty text={empty ?? 'No chart data'} />}</Panel>
}

export function TradesPage() {
  const { t } = useLang()
  const [period, setPeriod] = useState('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [symbol, setSymbol] = useState('')
  const [strategy, setStrategy] = useState('')
  const [side, setSide] = useState('')
  const [result, setResult] = useState('')
  const [exitReason, setExitReason] = useState('')
  const [page, setPage] = useState(0)
  const queryString = new URLSearchParams({ ...periodParams(period, startDate, endDate), limit: '50', offset: String(page * 50), ...(symbol ? { symbol } : {}), ...(strategy ? { strategy } : {}), ...(side ? { side } : {}), ...(result ? { result } : {}), ...(exitReason ? { exit_reason: exitReason } : {}) }).toString()
  const query = useQuery({ queryKey: ['trades', queryString], queryFn: () => getTrades(queryString) })
  const [selected, setSelected] = useState<Trade | null>(null)
  const filters = query.data?.filters
  return <><PageHeader eyebrow={t('JOURNAL','ЖУРНАЛ')} title={t('Trades','Сделки')}><PeriodPicker value={period} startDate={startDate} endDate={endDate} onChange={(value) => { setPeriod(value); setPage(0) }} onRangeChange={(start, end) => { setStartDate(start); setEndDate(end); setPage(0) }} /></PageHeader><div className="filter-bar"><select value={symbol} onChange={(event) => setSymbol(event.target.value)}><option value="">All symbols</option>{filters?.symbols.map((item) => <option key={item}>{item}</option>)}</select><select value={strategy} onChange={(event) => setStrategy(event.target.value)}><option value="">All strategies</option>{filters?.strategies.map((item) => <option key={item}>{item}</option>)}</select><select value={side} onChange={(event) => setSide(event.target.value)}><option value="">All sides</option><option value="long">Long</option><option value="short">Short</option></select><select value={result} onChange={(event) => setResult(event.target.value)}><option value="">All results</option><option value="win">Win</option><option value="loss">Loss</option></select><select value={exitReason} onChange={(event) => setExitReason(event.target.value)}><option value="">All exit reasons</option>{filters?.exit_reasons.map((item) => <option key={item}>{item}</option>)}</select></div><Panel title={`${query.data?.total ?? 0} trades`}><LoadingOrError loading={query.isPending} error={query.error} /><DataTable rows={query.data?.items ?? []} rowKey={(row) => row.trade_id} onRowClick={setSelected} renderCard={(row) => <><div className="card-line"><strong>{row.symbol}</strong><span>{row.strategy_id}</span><time>{fmtTs(row.closed_ts)}</time></div><div className="card-grid"><span>Side <b>{row.side}</b></span><span>PnL <b className={toneFor(row.pnl)}>{fmtUsd(row.pnl)}</b></span><span>R <b>{numberValue(row.r_multiple).toFixed(2)}</b></span><span>Duration <b>{fmtDuration(row.duration_sec)}</b></span></div></>} columns={[{ key: 'date', label: 'Date', render: (row) => fmtTs(row.closed_ts) }, { key: 'symbol', label: 'Symbol', render: (row) => <strong>{row.symbol}</strong> }, { key: 'strategy', label: 'Strategy', render: (row) => row.strategy_id ?? '—' }, { key: 'side', label: 'Side', render: (row) => row.side }, { key: 'entry', label: 'Entry', render: (row) => fmtPrice(row.entry_price) }, { key: 'exit', label: 'Exit', render: (row) => fmtPrice(row.exit_price) }, { key: 'sl', label: 'SL', render: (row) => fmtPrice(row.stop_loss) }, { key: 'tp', label: 'TP', render: (row) => fmtPrice(row.tp1) }, { key: 'qty', label: 'Size', render: (row) => <span className="cell-stack"><span>{fmtQty(row.qty)}</span><small>{fmtUsd(row.notional, false)}</small></span> }, { key: 'fees', label: 'Fees', render: (row) => <span>{fmtUsd(row.fees_actual ?? row.fees_est, false)}{row.fees_actual == null && <small className="muted"> est</small>}</span> }, { key: 'pnl', label: 'PnL', render: (row) => <span className={toneFor(row.pnl)}>{fmtUsd(row.pnl)}</span> }, { key: 'pnl-pct', label: 'PnL %', render: (row) => row.pnl_pct == null ? '—' : fmtPct(row.pnl_pct) }, { key: 'duration', label: 'Duration', render: (row) => fmtDuration(row.duration_sec) }, { key: 'r', label: 'R', render: (row) => numberValue(row.r_multiple).toFixed(2) }, { key: 'reason', label: 'Exit reason', render: (row) => row.exit_reason ?? '—' }]} /></Panel><div className="pagination"><button className="button tiny subtle" disabled={page === 0} onClick={() => setPage(page - 1)}>← Previous</button><span>Page {page + 1}</span><button className="button tiny subtle" disabled={!query.data || (page + 1) * 50 >= query.data.total} onClick={() => setPage(page + 1)}>Next →</button></div>{selected && <TradeDrawer trade={selected} onClose={() => setSelected(null)} />}</>
}

function TradeDrawer({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const query = useQuery({ queryKey: ['trade', trade.trade_id], queryFn: () => getTrade(trade.trade_id) })
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><aside className="drawer"><div className="drawer-heading"><div><span className="eyebrow">TRADE DETAIL</span><h2>{trade.symbol}</h2></div><button className="icon-button" onClick={onClose}>×</button></div>{query.data ? <><div className="detail-grid"><div>Trade ID <strong>{query.data.trade_id}</strong></div><div>Side <strong>{query.data.side}</strong></div><div>Entry <strong>{fmtPrice(query.data.entry_price)}</strong></div><div>Exit <strong>{fmtPrice(query.data.exit_price)}</strong></div><div>Size <strong>{fmtQty(query.data.qty)}</strong></div><div>Notional <strong>{fmtUsd(query.data.notional, false)}</strong></div><div>Opened <strong>{fmtTs(query.data.opened_ts)}</strong></div><div>Closed <strong>{fmtTs(query.data.closed_ts)}</strong></div><div>PnL <strong className={toneFor(query.data.pnl)}>{fmtUsd(query.data.pnl)}</strong></div><div>R multiple <strong>{query.data.r_multiple == null ? '—' : numberValue(query.data.r_multiple).toFixed(2)}</strong></div><div>Duration <strong>{fmtDuration(query.data.duration_sec)}</strong></div><div>Exit reason <strong>{query.data.exit_reason ?? '—'}</strong></div><div>PnL source <strong>{query.data.pnl_source ?? '—'}</strong></div><div>Fees <strong>{fmtUsd(query.data.fees_actual ?? query.data.fees_est, false)}{query.data.fees_actual == null ? ' (estimated)' : ''}</strong></div></div><Panel title="Signal details"><pre className="json-block">{JSON.stringify(query.data.signal_json ?? query.data.raw ?? {}, null, 2)}</pre></Panel><Panel title="Fills"><DataTable<Fill> rows={query.data.fills ?? []} rowKey={(row) => String(row.order_id ?? row.timestamp ?? row.ts ?? `${row.symbol}-${row.price}-${row.qty}`)} renderCard={(row) => <div className="card-grid"><span>Side <b>{row.side ?? '—'}</b></span><span>Qty <b>{row.qty ?? '—'}</b></span><span>Price <b>{fmtPrice(row.price)}</b></span><span>Fee <b>{fmtUsd(row.fee, false)}</b></span></div>} columns={[{ key: 'time', label: 'Time', render: (row) => fmtTs(row.timestamp ?? row.ts) }, { key: 'side', label: 'Side', render: (row) => row.side ?? '—' }, { key: 'qty', label: 'Qty', render: (row) => row.qty ?? '—' }, { key: 'price', label: 'Price', render: (row) => fmtPrice(row.price) }, { key: 'fee', label: 'Fee', render: (row) => fmtUsd(row.fee, false) }]} /></Panel><Panel title="Raw trade"><pre className="json-block">{JSON.stringify(query.data.raw ?? query.data, null, 2)}</pre></Panel><Panel title="Events"><EventList events={query.data.events ?? []} /></Panel></> : <div className="panel-loading">Loading trade…</div>}</aside></div>
}

export function EventsPage() {
  const { t } = useLang()
  const { events: liveEvents } = useLiveStore()
  const [level, setLevel] = useState('')
  const [eventType, setEventType] = useState('')
  const [symbol, setSymbol] = useState('')
  const [period, setPeriod] = useState('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [live, setLive] = useState(true)
  const queryString = new URLSearchParams({ ...periodParams(period, startDate, endDate), limit: '100', offset: '0', ...(level ? { level } : {}), ...(eventType ? { event_type: eventType } : {}), ...(symbol ? { symbol } : {}) }).toString()
  const query = useQuery({ queryKey: ['events', queryString], queryFn: () => getEvents(queryString) })
  const filteredLive = live ? liveEvents.filter((event) => (!level || event.level === level) && (!eventType || event.event_type === eventType) && (!symbol || event.symbol?.includes(symbol.toUpperCase()))) : []
  const items = [...filteredLive, ...(query.data?.items ?? [])].filter((event, index, all) => all.findIndex((item) => item.id === event.id) === index).slice(0, 100)
  return <><PageHeader eyebrow={t('OBSERVABILITY','НАБЛЮДЕНИЕ')} title={t('Events','События')}><div className="page-actions"><button className={clsx('button tiny', live ? 'primary' : 'subtle')} onClick={() => setLive(!live)}>● Live {live ? 'On' : 'Off'}</button><PeriodPicker value={period} startDate={startDate} endDate={endDate} onChange={setPeriod} onRangeChange={(start, end) => { setStartDate(start); setEndDate(end) }} /></div></PageHeader><div className="filter-bar"><select value={level} onChange={(event) => setLevel(event.target.value)}><option value="">All levels</option>{['INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((item) => <option key={item}>{item}</option>)}</select><select value={eventType} onChange={(event) => setEventType(event.target.value)}><option value="">All event types</option>{query.data?.event_types.map((item) => <option key={item}>{item}</option>)}</select><input placeholder="Symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} /></div><Panel title={`${query.data?.total ?? 0} events`}><DataTable rows={items} rowKey={(row) => String(row.id)} renderCard={(row) => <><div className="card-line"><span className={clsx('level', row.level.toLowerCase())}>{row.level}</span><strong>{row.event_type}</strong><time>{fmtTs(row.ts)}</time></div><p>{row.message}</p></>} columns={[{ key: 'time', label: 'Time', render: (row) => fmtTs(row.ts) }, { key: 'level', label: 'Level', render: (row) => <span className={clsx('level', row.level.toLowerCase())}>{row.level}</span> }, { key: 'type', label: 'Type', render: (row) => <span className="chip">{row.event_type}</span> }, { key: 'symbol', label: 'Symbol', render: (row) => row.symbol ?? '—' }, { key: 'strategy', label: 'Strategy', render: (row) => row.strategy_id ?? '—' }, { key: 'message', label: 'Message', render: (row) => <span className="truncate">{row.message}</span> }, { key: 'metadata', label: 'Metadata', render: (row) => row.metadata ? <details onClick={(event) => event.stopPropagation()}><summary>view</summary><pre className="json-inline">{JSON.stringify(row.metadata, null, 2)}</pre></details> : '—' }]} /></Panel></>
}

function clsx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}
