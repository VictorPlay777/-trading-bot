export type StatusName =
  | 'RUNNING'
  | 'STARTING'
  | 'PAUSED'
  | 'KILL_SWITCH'
  | 'CONNECTION_ERROR'
  | 'ERROR'
  | 'EMERGENCY_STOP'
  | 'STOPPED'

export interface Control {
  paused: boolean
  trading_enabled: boolean
  emergency_stop?: boolean
  kill_switch_triggered?: boolean
  kill_switch_reason?: string | null
}

export interface Risk {
  risk_per_trade_pct: number
  max_open_positions: number
  max_daily_loss_pct: number
  max_daily_loss_usd: number
  max_drawdown_pct: number
  max_position_notional_usdt: number
  max_leverage: number
  long_enabled: boolean
  short_enabled: boolean
  allowed_symbols: string[]
  kill_switch_enabled: boolean
  kill_switch_close_positions: boolean
  kill_switch_auto_reset_daily: boolean
}

export interface Status {
  status: StatusName
  state: StatusName
  substatus: string | null
  process_running: boolean
  pid: number | null
  managed: boolean
  strategy_id: string | null
  config_path: string | null
  last_heartbeat_ts: number | null
  heartbeat_age_sec: number | null
  cycle_ms: number | null
  uptime_sec: number | null
  bybit: {
    connected: boolean
    last_ok_ts: number | null
    last_error: string | null
  }
  control: Control
  risk: Risk
  kill_switch: KillSwitch
  warnings: string[]
  last_exit_code: number | null
}

export interface KillSwitch {
  day_start_equity?: number | null
  current_equity?: number | null
  peak_equity?: number | null
  triggered?: boolean
  triggered_reason?: string | null
  triggered_ts?: number | null
}

export interface Summary {
  status: Status
  wallet: {
    equity: number | null
    wallet_balance: number | null
    available_balance: number | null
    unrealized_pnl: number | null
  }
  pnl_today: number
  pnl_7d: number
  pnl_30d: number
  realized_pnl_all: number
  drawdown: { usd: number | null; pct: number | null }
  drawdown_source: string | null
  open_positions: number
  trades_today: number
  kill_switch: KillSwitch
  risk: Risk
  control: Control
}

export interface SummaryLight {
  equity: number | null
  unrealized: number | null
  open_positions: number
  pnl_today: number
  status: StatusName
}

export interface Position {
  symbol: string
  side: 'long' | 'short' | string
  qty: number
  entry_price: number
  mark_price: number
  unrealized_pnl: number
  leverage: number | string | null
  source?: 'bot' | 'exchange'
  notional?: number
  pnl_pct?: number
  r_multiple?: number
  stop_loss?: number | null
  tp1?: number | null
  tp2?: number | null
  tp3?: number | null
  opened_ts?: number | null
  strategy_id?: string | null
  exit_state?: string | null
  trailing_price?: number | null
  signal_json?: string | null
  [key: string]: unknown
}

export interface Fill {
  ts?: number
  timestamp?: number
  symbol?: string
  side?: string
  qty?: number
  price?: number
  fee?: number
  order_id?: string
  [key: string]: unknown
}

export interface LogLine {
  id: number
  ts: number
  level: string
  category: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR' | 'TRADE' | 'SYSTEM' | string
  message: string
  symbol?: string | null
}

export interface Event {
  id: number
  ts: number
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | string
  event_type: string
  message: string
  symbol?: string | null
  strategy_id?: string | null
  metadata?: unknown
  metadata_json?: string | null
}

export interface Trade {
  trade_id: string
  symbol: string
  strategy_id?: string | null
  side: string
  opened_ts: number
  closed_ts: number
  entry_price?: number | null
  exit_price?: number | null
  stop_loss?: number | null
  tp1?: number | null
  qty?: number | null
  notional?: number | null
  fees_actual?: number | null
  fees_est?: number | null
  pnl?: number | null
  pnl_pct?: number | null
  r_multiple?: number | null
  duration_sec?: number | null
  exit_reason?: string | null
  exit_reasons?: unknown
  pnl_source?: string | null
  signal_json?: string | null
  [key: string]: unknown
}

export interface Stats {
  metrics: {
    total_trades: number
    wins: number
    losses: number
    win_rate: number
    profit_factor: number | null
    expectancy: number
    avg_win: number
    avg_loss: number
    avg_r: number | null
    max_drawdown_usd: number
    max_drawdown_pct: number | null
    sharpe: number | null
    sharpe_note: string | null
    long_win_rate: number
    short_win_rate: number
    total_pnl: number
    total_fees: number
    fees_source: string
  }
  daily_pnl: Array<{ date: string; pnl: number; trades: number }>
  cumulative_pnl: Array<{ ts: number; cum_pnl: number }>
  drawdown: Array<{ ts: number; drawdown: number }>
  trades_per_day: Array<{ date: string; pnl: number; trades: number }>
  equity_curve: Array<Record<string, number | string | null>>
  by_strategy: Record<string, {
    trades: number
    win_rate: number
    pnl: number
    profit_factor: number | null
    max_drawdown: number
    max_drawdown_pct: number | null
    avg_r: number | null
    last_trade_ts: number | null
  }>
  notes: string[]
}

export interface TradeResponse {
  items: Trade[]
  total: number
  filters: {
    symbols: string[]
    strategies: string[]
    exit_reasons: string[]
  }
}

export interface EventResponse {
  items: Event[]
  total: number
  event_types: string[]
}

export interface Strategy {
  strategy_id: string
  active: boolean
  enabled: boolean
  running: boolean
  trades?: number
  win_rate?: number
  profit_factor?: number | null
  pnl?: number
  avg_r?: number | null
  max_drawdown?: number
  max_drawdown_pct?: number | null
  trades_today: number
  open_positions: number
  last_trade_ts?: number | null
  [key: string]: unknown
}

export interface StrategyField {
  name: string
  type: 'bool' | 'int' | 'float' | 'str' | string
  default: boolean | number | string
  current: boolean | number | string
  override: boolean
  dangerous: boolean
}

export interface StrategySettings {
  strategy_id: string
  fields: StrategyField[]
  applies_on: string
}

export interface RiskSchemaField {
  key: string
  type: string
  min: number
  max: number | null
  label: string
  dangerous: boolean
}

export interface RiskResponse extends Risk {
  schema: RiskSchemaField[]
}

export interface PositionDetail extends Position {
  open_orders: Array<Record<string, unknown>>
  fills: Fill[]
  events: Event[]
}

export interface TradeDetail extends Trade {
  raw?: unknown
  fills?: Fill[]
  events?: Event[]
}

export interface ApiErrorShape {
  detail?: string
}
