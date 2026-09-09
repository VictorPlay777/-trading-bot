import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, getResearch } from './api'
import { DataTable, Empty, ErrorState, KpiCard, PageHeader, Panel } from './components'
import { fmtPct, fmtPrice, fmtTs, fmtUsd, numberValue, toneFor } from './format'
import { useLang } from './i18n'

interface AggRow {
  key?: string | number
  signals?: number | null
  trades: number
  wins?: number
  losses?: number
  win_rate: number | null
  profit_factor: number | null
  expectancy: number | null
  expectancy_r: number | null
  avg_pnl?: number | null
  net_pnl?: number | null
  gross_pnl?: number | null
  avg_win?: number | null
  avg_loss?: number | null
  max_drawdown?: number | null
  avg_mae?: number | null
  avg_mfe?: number | null
  sharpe?: number | null
  sortino?: number | null
  sample_size: number
  sample_label: string
  symbol?: string
  long_wr?: number | null
  short_wr?: number | null
  regime?: string
  direction?: string
  confidence?: string
  adx?: string
  atr?: string
  status?: string
  [key: string]: unknown
}

const TABS = [
  ['overview', 'Overview', 'Обзор'],
  ['direction', 'Long vs Short', 'Лонг/Шорт'],
  ['confidence', 'Confidence', 'Уверенность'],
  ['regime', 'Regimes', 'Режимы'],
  ['regime-direction', 'Regime × Dir', 'Режим × Напр.'],
  ['confidence-regime', 'Conf × Regime', 'Conf × Режим'],
  ['symbols', 'Symbols', 'Монеты'],
  ['filters', 'Filters', 'Фильтры'],
  ['buckets:atr_bucket', 'Volatility', 'Волатильность'],
  ['buckets:funding_bucket', 'Funding', 'Фандинг'],
  ['buckets:oi_bucket', 'OI', 'Откр. интерес'],
  ['time', 'Time', 'Время'],
  ['edge-matrix', 'Edge Matrix', 'Матрица edge'],
  ['discovery', '🔬 Discovery', '🔬 Поиск edge'],
  ['symbol-edge', 'Symbol Edge', 'Edge по монетам'],
  ['filter-value', 'Filter Value', 'Ценность фильтров'],
  ['explain', 'Why?', 'Почему?'],
  ['report', 'Report', 'Отчёт'],
  ['signals', 'Signals', 'Сигналы'],
  ['trades', 'Trades', 'Сделки'],
]

function SampleChip({ label }: { label?: string }) {
  const tone = label === 'STRONGER SAMPLE' ? 'success' : label === 'MODERATE' ? 'info' : label === 'LOW CONFIDENCE' ? 'warning' : 'danger'
  return <span className={clsx('pill', tone)}>{label ?? '—'}</span>
}

function aggColumns(): Array<{ key: string; label: string; render: (row: AggRow) => React.ReactNode; className?: string }> {
  return [
    { key: 'n', label: 'N', render: (r) => <b>{r.trades}</b> },
    { key: 'sig', label: 'Signals', render: (r) => <span className="muted">{r.signals ?? '—'}</span> },
    { key: 'wr', label: 'WR', render: (r) => r.win_rate == null ? '—' : <span className={r.win_rate >= 0.5 ? 'profit' : 'loss'}>{fmtPct(r.win_rate * 100, 1)}</span> },
    { key: 'pf', label: 'PF', render: (r) => r.profit_factor == null ? '—' : <span className={r.profit_factor >= 1 ? 'profit' : 'loss'}>{numberValue(r.profit_factor).toFixed(2)}</span> },
    { key: 'exp', label: 'Expectancy', render: (r) => r.expectancy == null ? '—' : <b className={toneFor(r.expectancy)}>{fmtUsd(r.expectancy)}</b> },
    { key: 'expr', label: 'Exp (R)', render: (r) => r.expectancy_r == null ? '—' : <span className={toneFor(r.expectancy_r)}>{numberValue(r.expectancy_r).toFixed(2)}R</span> },
    { key: 'pnl', label: 'Net PnL', render: (r) => r.net_pnl == null ? '—' : <span className={toneFor(r.net_pnl)}>{fmtUsd(r.net_pnl)}</span> },
    { key: 'mae', label: 'Avg MAE', render: (r) => r.avg_mae == null ? '—' : fmtUsd(r.avg_mae, false) },
    { key: 'mfe', label: 'Avg MFE', render: (r) => r.avg_mfe == null ? '—' : fmtUsd(r.avg_mfe, false) },
    { key: 'sample', label: 'Sample', render: (r) => <SampleChip label={r.sample_label} /> },
  ]
}

function AggTable({ rows, labelKey = 'key' }: { rows: AggRow[]; labelKey?: string }) {
  if (!rows.length) return <Empty text="No data yet — statistics accumulate as the bot runs" />
  return <DataTable
    rows={rows}
    rowKey={(r) => String(r[labelKey] ?? r.symbol ?? JSON.stringify(r))}
    renderCard={(r) => <><div className="card-line"><strong>{String(r[labelKey] ?? r.symbol)}</strong><SampleChip label={r.sample_label} /></div><div className="card-grid"><span>Trades <b>{r.trades}</b></span><span>WR <b>{r.win_rate == null ? '—' : fmtPct(r.win_rate * 100, 1)}</b></span><span>Exp <b className={toneFor(r.expectancy)}>{fmtUsd(r.expectancy)}</b></span><span>PF <b>{r.profit_factor == null ? '—' : numberValue(r.profit_factor).toFixed(2)}</b></span></div></>}
    columns={[{ key: 'k', label: 'Group', render: (r) => <strong>{String(r[labelKey] ?? r.symbol ?? '—')}</strong> }, ...aggColumns()]}
  />
}

function BarPanel({ title, rows, dataKey, color = '#38bdf8' }: { title: string; rows: AggRow[]; dataKey: 'win_rate' | 'expectancy' | 'expectancy_r'; color?: string }) {
  const data = rows.filter((r) => r[dataKey] != null).map((r) => ({ name: String(r.key), value: dataKey === 'win_rate' ? (r[dataKey] as number) * 100 : r[dataKey] }))
  if (!data.length) return null
  return <Panel title={title}><div className="chart"><ResponsiveContainer width="100%" height={220}><BarChart data={data}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="name" stroke="#64748b" fontSize={10} /><YAxis stroke="#64748b" fontSize={10} /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Bar dataKey="value" radius={[3, 3, 0, 0]}>{data.map((row, i) => <Cell key={i} fill={numberValue(row.value) >= 0 ? color : '#f87171'} />)}</Bar></BarChart></ResponsiveContainer></div></Panel>
}

function OverviewTab() {
  const q = useQuery({ queryKey: ['research', 'overview'], queryFn: () => getResearch<AggRow & { allowed_signals: number; rejected_signals: number }>('overview'), refetchInterval: 15000 })
  const eq = useQuery({ queryKey: ['research', 'equity'], queryFn: () => getResearch<{ equity: Array<{ ts: number; equity: number }>; cumulative_pnl: Array<{ ts: number; cum_pnl: number }> }>('equity-curve'), refetchInterval: 30000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const d = q.data!
  return <>
    <div className="kpi-grid">
      <KpiCard label="Signals" value={d.signals ?? 0} sub={`${d.allowed_signals ?? 0} allowed · ${d.rejected_signals ?? 0} rejected`} />
      <KpiCard label="Trades" value={d.trades} sub={<SampleChip label={d.sample_label} />} />
      <KpiCard label="Win rate" value={d.win_rate == null ? '—' : fmtPct(d.win_rate * 100, 1)} tone={d.win_rate != null && d.win_rate >= 0.5 ? 'profit' : 'neutral'} />
      <KpiCard label="Profit factor" value={d.profit_factor == null ? '—' : numberValue(d.profit_factor).toFixed(2)} />
      <KpiCard label="Expectancy" value={fmtUsd(d.expectancy)} sub={d.expectancy_r != null ? `${numberValue(d.expectancy_r).toFixed(3)}R` : undefined} tone={toneFor(d.expectancy) === 'profit' ? 'profit' : toneFor(d.expectancy) === 'loss' ? 'loss' : 'neutral'} />
      <KpiCard label="Net PnL" value={fmtUsd(d.net_pnl)} tone={toneFor(d.net_pnl) === 'profit' ? 'profit' : 'loss'} />
      <KpiCard label="Avg win / loss" value={`${fmtUsd(d.avg_win)} / ${fmtUsd(d.avg_loss, false)}`} />
      <KpiCard label="Median PnL" value={fmtUsd(d.median_pnl)} />
      <KpiCard label="Max win" value={fmtUsd(d.max_win)} tone="profit" />
      <KpiCard label="Max loss" value={fmtUsd(d.max_loss)} tone="loss" />
      <KpiCard label="Max drawdown" value={fmtUsd(d.max_drawdown, false)} tone="loss" />
      <KpiCard label="Sharpe / Sortino" value={`${d.sharpe == null ? '—' : numberValue(d.sharpe).toFixed(2)} / ${d.sortino == null ? '—' : numberValue(d.sortino).toFixed(2)}`} sub={d.trades < 30 ? 'unstable — small sample' : undefined} />
    </div>
    <div className="chart-grid">
      <Panel title="Equity curve">{eq.data?.equity?.length ? <div className="chart"><ResponsiveContainer width="100%" height={240}><LineChart data={eq.data.equity}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="ts" tickFormatter={(v) => fmtTs(v)} stroke="#64748b" fontSize={10} /><YAxis stroke="#64748b" fontSize={10} domain={['auto', 'auto']} /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Line type="monotone" dataKey="equity" stroke="#38bdf8" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div> : <Empty text="No equity history yet" />}</Panel>
      <Panel title="Cumulative PnL">{eq.data?.cumulative_pnl?.length ? <div className="chart"><ResponsiveContainer width="100%" height={240}><LineChart data={eq.data.cumulative_pnl}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="ts" tickFormatter={(v) => fmtTs(v)} stroke="#64748b" fontSize={10} /><YAxis stroke="#64748b" fontSize={10} /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Line type="monotone" dataKey="cum_pnl" stroke="#4ade80" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div> : <Empty text="No closed trades yet" />}</Panel>
    </div>
  </>
}

function DirectionTab() {
  const q = useQuery({ queryKey: ['research', 'direction'], queryFn: () => getResearch<{ long: AggRow; short: AggRow; all: AggRow }>('direction'), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = (['long', 'short'] as const).map((d) => ({ key: d.toUpperCase(), ...q.data![d] }))
  const chartData = rows.map((r) => ({ name: r.key, wr: (r.win_rate ?? 0) * 100, exp: r.expectancy ?? 0 }))
  return <>
    <div className="chart-grid">
      <Panel title="Win rate: LONG vs SHORT"><div className="chart"><ResponsiveContainer width="100%" height={220}><BarChart data={chartData}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="name" stroke="#64748b" /><YAxis stroke="#64748b" /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Bar dataKey="wr" name="WR %" radius={[3, 3, 0, 0]}>{chartData.map((_, i) => <Cell key={i} fill={i === 0 ? '#4ade80' : '#f87171'} />)}</Bar></BarChart></ResponsiveContainer></div></Panel>
      <Panel title="Expectancy: LONG vs SHORT"><div className="chart"><ResponsiveContainer width="100%" height={220}><BarChart data={chartData}><CartesianGrid stroke="#1e293b" vertical={false} /><XAxis dataKey="name" stroke="#64748b" /><YAxis stroke="#64748b" /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} /><Bar dataKey="exp" name="Expectancy $" radius={[3, 3, 0, 0]}>{chartData.map((r, i) => <Cell key={i} fill={r.exp >= 0 ? '#4ade80' : '#f87171'} />)}</Bar></BarChart></ResponsiveContainer></div></Panel>
    </div>
    <Panel title="By direction"><AggTable rows={rows} /></Panel>
  </>
}

function SimpleAggTab({ section, field, title }: { section: string; field?: string; title: string }) {
  const path = section === 'buckets' ? `buckets?field=${field}` : section
  const q = useQuery({ queryKey: ['research', path], queryFn: () => getResearch<{ rows: AggRow[] }>(path.includes('?') ? path.split('?')[0] : path, path.includes('?') ? path.split('?')[1] : ''), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = q.data?.rows ?? []
  return <>
    <div className="chart-grid">
      <BarPanel title={`Win rate — ${title}`} rows={rows} dataKey="win_rate" color="#38bdf8" />
      <BarPanel title={`Expectancy — ${title}`} rows={rows} dataKey="expectancy" color="#4ade80" />
    </div>
    <Panel title={title}><AggTable rows={rows} /></Panel>
  </>
}

function RegimeDirectionTab() {
  const q = useQuery({ queryKey: ['research', 'regime-direction'], queryFn: () => getResearch<{ matrix: Record<string, Record<string, { trades: number; win_rate: number | null; expectancy: number | null; expectancy_r: number | null; profit_factor: number | null; sample_label: string }>> }>('regime-direction'), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const matrix = q.data?.matrix ?? {}
  const regimes = Object.keys(matrix)
  return <Panel title="Regime × Direction (expectancy per trade)">
    <div className="table-wrap"><table className="data-table heat-table">
      <thead><tr><th>Regime</th><th>LONG</th><th>SHORT</th></tr></thead>
      <tbody>{regimes.map((reg) => <tr key={reg}><td><strong>{reg.toUpperCase()}</strong></td>{(['long', 'short'] as const).map((d) => {
        const cell = matrix[reg]?.[d]
        const exp = cell?.expectancy ?? null
        const cls = exp == null || cell.trades === 0 ? '' : exp > 0 ? 'heat-pos' : 'heat-neg'
        return <td key={d} className={cls}><div className="heat-cell"><b>{exp == null ? '—' : fmtUsd(exp)}</b><small>{cell.trades} trades · WR {cell.win_rate == null ? '—' : fmtPct(cell.win_rate * 100, 0)}</small><SampleChip label={cell.sample_label} /></div></td>
      })}</tr>)}</tbody>
    </table></div>
  </Panel>
}

function ConfRegimeTab() {
  const q = useQuery({ queryKey: ['research', 'conf-regime'], queryFn: () => getResearch<{ rows: AggRow[] }>('confidence-regime'), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = (q.data?.rows ?? []).map((r) => ({ ...r, key: `${r.regime} · ${r.confidence_bucket}` }))
  return <Panel title="Confidence × Regime"><AggTable rows={rows} /></Panel>
}

function SymbolsTab() {
  const q = useQuery({ queryKey: ['research', 'symbols'], queryFn: () => getResearch<{ rows: AggRow[] }>('symbols'), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = q.data?.rows ?? []
  return <>
    <BarPanel title="Net PnL by symbol" rows={rows.map((r) => ({ ...r, key: r.symbol }))} dataKey="expectancy" />
    <Panel title="Per-symbol performance"><DataTable
      rows={rows} rowKey={(r) => String(r.symbol)}
      renderCard={(r) => <><div className="card-line"><strong>{r.symbol}</strong><SampleChip label={r.sample_label} /></div><div className="card-grid"><span>Trades <b>{r.trades}</b></span><span>WR <b>{r.win_rate == null ? '—' : fmtPct(r.win_rate * 100, 1)}</b></span><span>PnL <b className={toneFor(r.net_pnl)}>{fmtUsd(r.net_pnl)}</b></span></div></>}
      columns={[
        { key: 'sym', label: 'Symbol', render: (r) => <strong>{r.symbol}</strong> },
        { key: 'sig', label: 'Signals', render: (r) => r.signals ?? '—' },
        { key: 'n', label: 'Trades', render: (r) => r.trades },
        { key: 'lwr', label: 'LONG WR', render: (r) => r.long_wr == null ? '—' : fmtPct(r.long_wr * 100, 1) },
        { key: 'swr', label: 'SHORT WR', render: (r) => r.short_wr == null ? '—' : fmtPct(r.short_wr * 100, 1) },
        ...aggColumns().slice(2),
      ]} /></Panel>
  </>
}

interface FilterRow { filter: string; rejected: number; sole_reason: number; share_of_rejected: number | null }

function FiltersTab() {
  const q = useQuery({ queryKey: ['research', 'filters'], queryFn: () => getResearch<{ rows: FilterRow[]; total_signals: number; total_rejected: number }>('filters'), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const d = q.data!
  return <>
    <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
      <KpiCard label="Total signals" value={d.total_signals} />
      <KpiCard label="Rejected" value={d.total_rejected} />
      <KpiCard label="Rejection rate" value={d.total_signals ? fmtPct(d.total_rejected / d.total_signals * 100, 1) : '—'} />
    </div>
    <Panel title="Filter funnel — how many signals each gate blocks">
      <p className="muted note">A signal can fail several gates at once — all reasons are recorded. «sole» = this filter was the only blocker (that signal would have traded without it).</p>
      <DataTable rows={d.rows} rowKey={(r) => r.filter}
        renderCard={(r) => <div className="card-line"><strong>{r.filter}</strong><span>{r.rejected} rejected</span></div>}
        columns={[
          { key: 'f', label: 'Filter', render: (r) => <strong>{r.filter}</strong> },
          { key: 'rej', label: 'Rejected', render: (r) => r.rejected },
          { key: 'sole', label: 'Sole reason', render: (r) => r.sole_reason },
          { key: 'share', label: 'Share of rejects', render: (r) => r.share_of_rejected == null ? '—' : fmtPct(r.share_of_rejected * 100, 1) },
        ]} />
    </Panel>
  </>
}

function TimeTab() {
  const q = useQuery({ queryKey: ['research', 'time'], queryFn: () => getResearch<{ by_hour: AggRow[]; by_dow: AggRow[] }>('time'), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const dow = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const hours = (q.data?.by_hour ?? []).map((r) => ({ ...r, key: `${r.key}:00` }))
  const days = (q.data?.by_dow ?? []).map((r) => ({ ...r, key: dow[numberValue(r.key)] ?? String(r.key) }))
  return <>
    <div className="chart-grid">
      <BarPanel title="Expectancy by hour (UTC)" rows={hours} dataKey="expectancy" />
      <BarPanel title="Expectancy by weekday" rows={days} dataKey="expectancy" />
    </div>
    <Panel title="By hour (UTC)"><AggTable rows={hours} /></Panel>
    <Panel title="By weekday"><AggTable rows={days} /></Panel>
  </>
}

function EdgeMatrixTab() {
  const [minTrades, setMinTrades] = useState(5)
  const q = useQuery({ queryKey: ['research', 'edge', minTrades], queryFn: () => getResearch<{ rows: AggRow[] }>('edge-matrix', `min_trades=${minTrades}`), refetchInterval: 15000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = (q.data?.rows ?? []).map((r, i) => ({ ...r, key: i }))
  const statusTone = (s?: string) => s === 'PROMISING' ? 'success' : s === 'BAD' ? 'danger' : s === 'INSUFFICIENT' ? 'muted' : 'info'
  return <>
    <div className="filter-bar"><label className="checkbox-row">Min trades: <input type="number" style={{ width: 70 }} value={minTrades} min={1} onChange={(e) => setMinTrades(Math.max(1, Number(e.target.value) || 1))} /></label><span className="muted">Sorted by expectancy (R). Combinations need real sample size before any conclusion.</span></div>
    <Panel title="Edge matrix — regime × direction × confidence × ADX × ATR">
      <DataTable rows={rows} rowKey={(r) => String(r.key)}
        renderCard={(r) => <><div className="card-line"><strong>{r.regime} {r.direction} {r.confidence}</strong><span className={clsx('pill', statusTone(r.status))}>{r.status}</span></div><div className="card-grid"><span>Trades <b>{r.trades}</b></span><span>WR <b>{r.win_rate == null ? '—' : fmtPct(r.win_rate * 100, 1)}</b></span><span>Exp R <b>{r.expectancy_r == null ? '—' : numberValue(r.expectancy_r).toFixed(2)}</b></span></div></>}
        columns={[
          { key: 'reg', label: 'Regime', render: (r) => <strong>{r.regime}</strong> },
          { key: 'dir', label: 'Dir', render: (r) => r.direction },
          { key: 'conf', label: 'Confidence', render: (r) => r.confidence },
          { key: 'adx', label: 'ADX', render: (r) => r.adx },
          { key: 'atr', label: 'ATR', render: (r) => r.atr },
          { key: 'n', label: 'Trades', render: (r) => <b>{r.trades}</b> },
          { key: 'wr', label: 'WR', render: (r) => r.win_rate == null ? '—' : fmtPct(r.win_rate * 100, 1) },
          { key: 'pf', label: 'PF', render: (r) => r.profit_factor == null ? '—' : numberValue(r.profit_factor).toFixed(2) },
          { key: 'exp', label: 'Expectancy', render: (r) => <b className={toneFor(r.expectancy)}>{fmtUsd(r.expectancy)}</b> },
          { key: 'expr', label: 'Exp R', render: (r) => r.expectancy_r == null ? '—' : <span className={toneFor(r.expectancy_r)}>{numberValue(r.expectancy_r).toFixed(2)}R</span> },
          { key: 'pnl', label: 'Net PnL', render: (r) => <span className={toneFor(r.net_pnl)}>{fmtUsd(r.net_pnl)}</span> },
          { key: 'sample', label: 'Sample', render: (r) => <SampleChip label={r.sample_label} /> },
          { key: 'st', label: 'Status', render: (r) => <span className={clsx('pill', statusTone(r.status))}>{r.status}</span> },
        ]} />
    </Panel>
  </>
}

function SignalsTab() {
  const q = useQuery({ queryKey: ['research', 'signals'], queryFn: () => getResearch<{ items: Array<Record<string, unknown>> }>('signals', 'limit=100'), refetchInterval: 10000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = q.data?.items ?? []
  return <Panel title={`Signal snapshots (latest ${rows.length})`}>
    <DataTable rows={rows} rowKey={(r) => String(r.id)}
      renderCard={(r) => <><div className="card-line"><strong>{String(r.symbol)}</strong><span>{String(r.direction)}</span><span className={r.allowed ? 'profit' : 'loss'}>{r.allowed ? 'ALLOWED' : 'REJECTED'}</span></div><p className="muted">{String(r.rejection_reason ?? '')}</p></>}
      columns={[
        { key: 'ts', label: 'Time', render: (r) => fmtTs(r.ts) },
        { key: 'sym', label: 'Symbol', render: (r) => <strong>{String(r.symbol)}</strong> },
        { key: 'dir', label: 'Dir', render: (r) => String(r.direction ?? '—') },
        { key: 'conf', label: 'Conf', render: (r) => r.confidence == null ? '—' : numberValue(r.confidence).toFixed(3) },
        { key: 'agr', label: 'Agr', render: (r) => String(r.agreement ?? '—') },
        { key: 'reg', label: 'Regime', render: (r) => String(r.regime ?? '—') },
        { key: 'adx', label: 'ADX', render: (r) => r.adx == null ? '—' : numberValue(r.adx).toFixed(1) },
        { key: 'ev', label: 'EV', render: (r) => r.ev == null ? '—' : numberValue(r.ev).toFixed(4) },
        { key: 'allow', label: 'Decision', render: (r) => r.allowed ? <span className="profit">ALLOWED</span> : <span className="loss">REJ</span> },
        { key: 'reason', label: 'Reasons', render: (r) => <span className="truncate">{String(r.rejection_reasons_json ?? r.rejection_reason ?? '—')}</span> },
      ]} />
  </Panel>
}

function TradesTab() {
  const q = useQuery({ queryKey: ['research', 'trades-list'], queryFn: () => api<{ items: Array<Record<string, unknown>> }>('/api/trades?limit=100'), refetchInterval: 10000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = q.data?.items ?? []
  return <Panel title={`Recent trades (latest ${rows.length})`}>
    <DataTable rows={rows} rowKey={(r) => String(r.trade_id)}
      renderCard={(r) => <><div className="card-line"><strong>{String(r.symbol)}</strong><span>{String(r.side)}</span><b className={toneFor(r.pnl)}>{fmtUsd(r.pnl)}</b></div><p className="muted">{String(r.exit_reason ?? '')}</p></>}
      columns={[
        { key: 'ts', label: 'Closed', render: (r) => fmtTs(r.closed_ts) },
        { key: 'sym', label: 'Symbol', render: (r) => <strong>{String(r.symbol)}</strong> },
        { key: 'side', label: 'Side', render: (r) => String(r.side) },
        { key: 'entry', label: 'Entry', render: (r) => fmtPrice(r.entry_price) },
        { key: 'exit', label: 'Exit', render: (r) => fmtPrice(r.exit_price) },
        { key: 'pnl', label: 'Net PnL', render: (r) => <b className={toneFor(r.pnl)}>{fmtUsd(r.pnl)}</b> },
        { key: 'res', label: 'Result', render: (r) => <span className={clsx('pill', r.result === 'WIN' ? 'success' : r.result === 'LOSS' ? 'danger' : 'muted')}>{String(r.result ?? '—')}</span> },
        { key: 'rr', label: 'PnL R', render: (r) => r.r_multiple == null ? '—' : `${numberValue(r.r_multiple).toFixed(2)}R` },
        { key: 'mae', label: 'MAE', render: (r) => r.mae == null ? '—' : fmtUsd(r.mae, false) },
        { key: 'mfe', label: 'MFE', render: (r) => r.mfe == null ? '—' : fmtUsd(r.mfe, false) },
        { key: 'sig', label: 'Signal', render: (r) => r.signal_snapshot_id ? `#${r.signal_snapshot_id}` : '—' },
        { key: 'reason', label: 'Exit reason', render: (r) => <span className="truncate">{String(r.exit_reason ?? '—')}</span> },
      ]} />
  </Panel>
}

// ---------------------------------------------------------------------------
// Edge discovery tabs
// ---------------------------------------------------------------------------

interface CfRow {
  key: string | number | Array<unknown>
  n: number
  wins?: number
  win_rate: number | null
  profit_factor: number | null
  expectancy_r: number | null
  in_sample_r?: number | null
  oos_r?: number | null
  symbol_breadth?: number | null
  symbols?: number
  sample_label: string
  evidence: string
  label?: string
  group?: string
}

function EvidenceChip({ label }: { label?: string }) {
  const tone = label === 'OBSERVED EDGE' ? 'success' : label === 'POSSIBLE EDGE' ? 'info'
    : label === 'WEAK EVIDENCE' ? 'warning' : label === 'NEGATIVE EDGE' ? 'danger' : 'muted'
  return <span className={clsx('pill', tone)}>{label ?? '—'}</span>
}

function CfTable({ rows, label }: { rows: CfRow[]; label?: string }) {
  if (!rows.length) return <Empty text="No counterfactual outcomes yet — they appear ~10 min after each signal" />
  return <DataTable rows={rows} rowKey={(r) => String(r.label ?? JSON.stringify(r.key))}
    renderCard={(r) => <><div className="card-line"><strong>{r.label ?? String(r.key)}</strong><EvidenceChip label={r.evidence} /></div><div className="card-grid"><span>N <b>{r.n}</b></span><span>WR <b>{r.win_rate == null ? '—' : fmtPct(r.win_rate * 100, 1)}</b></span><span>Exp <b className={toneFor(r.expectancy_r)}>{r.expectancy_r == null ? '—' : `${numberValue(r.expectancy_r).toFixed(2)}R`}</b></span></div></>}
    columns={[
      { key: 'k', label: label ?? 'Group', render: (r) => <strong>{r.label ?? (Array.isArray(r.key) ? r.key.join(' + ') : String(r.key))}</strong> },
      { key: 'n', label: 'N', render: (r) => <b>{r.n}</b> },
      { key: 'wr', label: 'WR', render: (r) => r.win_rate == null ? '—' : <span className={r.win_rate >= 0.5 ? 'profit' : 'loss'}>{fmtPct(r.win_rate * 100, 1)}</span> },
      { key: 'pf', label: 'PF', render: (r) => r.profit_factor == null ? '—' : numberValue(r.profit_factor).toFixed(2) },
      { key: 'exp', label: 'Exp (R)', render: (r) => r.expectancy_r == null ? '—' : <b className={toneFor(r.expectancy_r)}>{numberValue(r.expectancy_r).toFixed(2)}R</b> },
      { key: 'is', label: 'IS', render: (r) => r.in_sample_r == null ? '—' : `${numberValue(r.in_sample_r).toFixed(2)}R` },
      { key: 'oos', label: 'OOS', render: (r) => r.oos_r == null ? '—' : `${numberValue(r.oos_r).toFixed(2)}R` },
      { key: 'br', label: 'Symbols+', render: (r) => r.symbol_breadth == null ? '—' : fmtPct(r.symbol_breadth * 100, 0) },
      { key: 'ev', label: 'Evidence', render: (r) => <EvidenceChip label={r.evidence} /> },
    ]} />
}

function DiscoveryTab() {
  const q = useQuery({ queryKey: ['research', 'edge-discovery'], queryFn: () => getResearch<{
    baseline: { n: number; win_rate: number | null; expectancy_r: number | null }
    level1: Record<string, CfRow[]>
    level2: Record<string, CfRow[]>
    level3: Record<string, CfRow[]>
    top_edges: CfRow[]
    worst_edges: CfRow[]
  }>('edge-discovery'), refetchInterval: 30000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const d = q.data!
  const lvl1Names: Record<string, string> = { direction: 'Direction', regime: 'Regime', confidence: 'Confidence', adx: 'ADX', atr: 'ATR%', volume: 'Volume', funding: 'Funding', oi: 'OI change', depth: 'Depth', imbalance: 'Orderbook imbalance', momentum: 'Momentum (10 bars)' }
  return <>
    <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
      <KpiCard label="Signals with outcome" value={d.baseline.n} sub="counterfactual, all signals" />
      <KpiCard label="Baseline WR" value={d.baseline.win_rate == null ? '—' : fmtPct(d.baseline.win_rate * 100, 1)} />
      <KpiCard label="Baseline expectancy" value={d.baseline.expectancy_r == null ? '—' : `${numberValue(d.baseline.expectancy_r).toFixed(3)}R`} tone={toneFor(d.baseline.expectancy_r) === 'loss' ? 'loss' : 'neutral'} />
    </div>
    <Panel title="🟢 Top observed edges (combos, sorted by expectancy R)"><CfTable rows={d.top_edges} label="Combination" /></Panel>
    <Panel title="🔴 Worst / losing combinations"><CfTable rows={d.worst_edges} label="Combination" /></Panel>
    <Panel title="Level 2 — factor pairs">
      {Object.entries(d.level2).map(([name, rows]) => <details key={name} style={{ marginBottom: 8 }}><summary style={{ cursor: 'pointer', fontWeight: 600 }}>{name.replaceAll('_', ' + ')}</summary><CfTable rows={rows} /></details>)}
    </Panel>
    <Panel title="Level 1 — single factors">
      {Object.entries(d.level1).map(([name, rows]) => <details key={name} style={{ marginBottom: 8 }}><summary style={{ cursor: 'pointer', fontWeight: 600 }}>{lvl1Names[name] ?? name}</summary><CfTable rows={rows} /></details>)}
    </Panel>
    <p className="muted note">Metrics are counterfactual: hypothetical TP=SL=0.5×ATR brackets evaluated on the 10 bars after each signal — including rejected ones. IS/OOS = first/second half of the period. «Symbols+» = share of symbols with positive expectancy.</p>
  </>
}

interface SymEdge { symbol: string; long: { n: number; win_rate: number | null; expectancy_r: number | null; sample_label: string }; short: { n: number; win_rate: number | null; expectancy_r: number | null; sample_label: string } }

function SymbolEdgeTab() {
  const q = useQuery({ queryKey: ['research', 'symbol-edge'], queryFn: () => getResearch<{ rows: SymEdge[] }>('symbol-edge'), refetchInterval: 30000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = q.data?.rows ?? []
  return <Panel title="Symbol edge — counterfactual per direction">
    <DataTable rows={rows} rowKey={(r) => r.symbol}
      renderCard={(r) => <><div className="card-line"><strong>{r.symbol}</strong></div><div className="card-grid"><span>LONG <b>{r.long.win_rate == null ? '—' : `${fmtPct(r.long.win_rate * 100, 0)} ${numberValue(r.long.expectancy_r).toFixed(2)}R`}</b></span><span>SHORT <b>{r.short.win_rate == null ? '—' : `${fmtPct(r.short.win_rate * 100, 0)} ${numberValue(r.short.expectancy_r).toFixed(2)}R`}</b></span></div></>}
      columns={[
        { key: 's', label: 'Symbol', render: (r) => <strong>{r.symbol}</strong> },
        { key: 'l', label: 'LONG', render: (r) => r.long.n === 0 ? '—' : <span className={toneFor(r.long.expectancy_r)}>{fmtPct((r.long.win_rate ?? 0) * 100, 0)} · {numberValue(r.long.expectancy_r).toFixed(2)}R <small className="muted">n={r.long.n}</small></span> },
        { key: 'sh', label: 'SHORT', render: (r) => r.short.n === 0 ? '—' : <span className={toneFor(r.short.expectancy_r)}>{fmtPct((r.short.win_rate ?? 0) * 100, 0)} · {numberValue(r.short.expectancy_r).toFixed(2)}R <small className="muted">n={r.short.n}</small></span> },
        { key: 'ls', label: 'LONG sample', render: (r) => <SampleChip label={r.long.sample_label} /> },
        { key: 'ss', label: 'SHORT sample', render: (r) => <SampleChip label={r.short.sample_label} /> },
      ]} />
  </Panel>
}

interface FvRow { filter: string; rejected: number; with_outcome: number; would_win: number; would_lose: number; would_win_rate: number | null; cf_expectancy_r: number | null; verdict: string; sample_label: string }

function FilterValueTab() {
  const q = useQuery({ queryKey: ['research', 'filter-value'], queryFn: () => getResearch<{ rows: FvRow[] }>('filter-value'), refetchInterval: 30000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const rows = q.data?.rows ?? []
  const vTone = (v: string) => v === 'FILTER HELPS' ? 'success' : v === 'FILTER HURTS' ? 'danger' : 'muted'
  return <Panel title="Filter value — what would blocked signals have done?">
    <p className="muted note">Counterfactual: if the rejected signal had been taken (TP=SL=0.5×ATR, next 10 bars), would it have won? A good filter blocks losers (cf expectancy &lt; 0 → HELPS); a bad filter blocks winners (HURTS).</p>
    <DataTable rows={rows} rowKey={(r) => r.filter}
      renderCard={(r) => <><div className="card-line"><strong>{r.filter}</strong><span className={clsx('pill', vTone(r.verdict))}>{r.verdict}</span></div><div className="card-grid"><span>Rejected <b>{r.rejected}</b></span><span>Would win <b>{r.would_win_rate == null ? '—' : fmtPct(r.would_win_rate * 100, 1)}</b></span></div></>}
      columns={[
        { key: 'f', label: 'Filter', render: (r) => <strong>{r.filter}</strong> },
        { key: 'rej', label: 'Rejected', render: (r) => r.rejected },
        { key: 'out', label: 'With outcome', render: (r) => r.with_outcome },
        { key: 'ww', label: 'Would win', render: (r) => r.would_win },
        { key: 'wl', label: 'Would lose', render: (r) => r.would_lose },
        { key: 'wr', label: 'Would-win %', render: (r) => r.would_win_rate == null ? '—' : fmtPct(r.would_win_rate * 100, 1) },
        { key: 'exp', label: 'Cf. Exp (R)', render: (r) => r.cf_expectancy_r == null ? '—' : <b className={toneFor(r.cf_expectancy_r)}>{numberValue(r.cf_expectancy_r).toFixed(2)}R</b> },
        { key: 'v', label: 'Verdict', render: (r) => <span className={clsx('pill', vTone(r.verdict))}>{r.verdict}</span> },
        { key: 's', label: 'Sample', render: (r) => <SampleChip label={r.sample_label} /> },
      ]} />
  </Panel>
}

interface ExplainResp {
  error?: string
  trade: Record<string, unknown>
  signal: Record<string, unknown> | null
  checks: Array<{ factor: string; value: unknown; mark: string }>
  result_r: number | null
  result: string | null
}

function ExplainTab() {
  const [tradeId, setTradeId] = useState('')
  const [submitted, setSubmitted] = useState('')
  const q = useQuery({ queryKey: ['research', 'explain', submitted], queryFn: () => getResearch<ExplainResp>('trade-explain', `trade_id=${encodeURIComponent(submitted)}`), enabled: !!submitted })
  return <>
    <div className="filter-bar">
      <input placeholder="trade_id (e.g. BTCUSDT_1788812345)" style={{ minWidth: 300 }} value={tradeId} onChange={(e) => setTradeId(e.target.value)} />
      <button className="button" onClick={() => setSubmitted(tradeId.trim())}>Explain</button>
    </div>
    {q.data?.error && <ErrorState message={q.data.error} />}
    {q.data && !q.data.error && <Panel title={`${q.data.trade.symbol} ${String(q.data.trade.side).toUpperCase()} — ${q.data.result ?? '—'} ${q.data.result_r != null ? `(${numberValue(q.data.result_r).toFixed(2)}R)` : ''}`}>
      {!q.data.signal && <p className="muted note">No linked signal snapshot (older trade) — showing limited factors.</p>}
      <div className="table-wrap"><table className="data-table">
        <thead><tr><th>Factor</th><th>Value</th><th>Mark</th></tr></thead>
        <tbody>{q.data.checks.map((c) => <tr key={c.factor}><td>{c.factor}</td><td>{String(c.value)}</td><td>{c.mark === 'good' ? '✓' : '⚠'}</td></tr>)}</tbody>
      </table></div>
    </Panel>}
  </>
}

function ReportTab() {
  const q = useQuery({ queryKey: ['research', 'edge-report'], queryFn: () => getResearch<{
    period: string
    by_period: Record<string, { n: number; win_rate: number | null; expectancy_r: number | null }>
    top_edges: CfRow[]
    worst_edges: CfRow[]
    baseline: { n: number; win_rate: number | null; expectancy_r: number | null }
  }>('edge-report'), refetchInterval: 60000 })
  if (q.isPending) return <div className="panel-loading">Loading…</div>
  if (q.error) return <ErrorState message={q.error.message} />
  const d = q.data!
  return <>
    <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
      {Object.entries(d.by_period).map(([name, p]) => <KpiCard key={name} label={`Last ${name}`} value={p.expectancy_r == null ? '—' : `${numberValue(p.expectancy_r).toFixed(3)}R`} sub={`n=${p.n} · WR ${p.win_rate == null ? '—' : fmtPct(p.win_rate * 100, 0)}`} tone={toneFor(p.expectancy_r) === 'loss' ? 'loss' : 'neutral'} />)}
      <KpiCard label="Baseline (all signals)" value={d.baseline.expectancy_r == null ? '—' : `${numberValue(d.baseline.expectancy_r).toFixed(3)}R`} sub={`n=${d.baseline.n}`} />
    </div>
    <Panel title="BEST CONDITIONS"><CfTable rows={d.top_edges} label="Condition" /></Panel>
    <Panel title="WORST / FAILED CONDITIONS"><CfTable rows={d.worst_edges} label="Condition" /></Panel>
  </>
}

export function ResearchPage() {
  const [tab, setTab] = useState<string>('overview')
  const { t, lang } = useLang()
  return <>
    <PageHeader eyebrow={t('RESEARCH', 'ИССЛЕДОВАНИЕ')} title={t('Strategy Analytics', 'Аналитика стратегии')} />
    <div className="filter-bar research-tabs">
      {TABS.map(([id, label, ru]) => <button key={id} className={clsx('button tiny', tab === id && 'selected')} onClick={() => setTab(id)}>{lang === 'ru' && ru ? ru : label}</button>)}
    </div>
    {tab === 'overview' && <OverviewTab />}
    {tab === 'direction' && <DirectionTab />}
    {tab === 'confidence' && <SimpleAggTab section="confidence" title="Confidence buckets" />}
    {tab === 'regime' && <SimpleAggTab section="regime" title="Market regime" />}
    {tab === 'regime-direction' && <RegimeDirectionTab />}
    {tab === 'confidence-regime' && <ConfRegimeTab />}
    {tab === 'symbols' && <SymbolsTab />}
    {tab === 'filters' && <FiltersTab />}
    {tab === 'buckets:atr_bucket' && <SimpleAggTab section="buckets" field="atr_bucket" title="Volatility (ATR%)" />}
    {tab === 'buckets:funding_bucket' && <SimpleAggTab section="buckets" field="funding_bucket" title="Funding rate" />}
    {tab === 'buckets:oi_bucket' && <SimpleAggTab section="buckets" field="oi_bucket" title="Open interest change" />}
    {tab === 'time' && <TimeTab />}
    {tab === 'edge-matrix' && <EdgeMatrixTab />}
    {tab === 'discovery' && <DiscoveryTab />}
    {tab === 'symbol-edge' && <SymbolEdgeTab />}
    {tab === 'filter-value' && <FilterValueTab />}
    {tab === 'explain' && <ExplainTab />}
    {tab === 'report' && <ReportTab />}
    {tab === 'signals' && <SignalsTab />}
    {tab === 'trades' && <TradesTab />}
  </>
}
