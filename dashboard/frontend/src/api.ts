import type {
  EventResponse,
  LogLine,
  Position,
  PositionDetail,
  RiskResponse,
  Stats,
  Status,
  Strategy,
  StrategySettings,
  Summary,
  TradeDetail,
  TradeResponse,
} from './types'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-Requested-With', 'dashboard')
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { ...init, headers, credentials: 'include' })
  if (response.status === 401) {
    if (window.location.pathname !== '/login') {
      window.location.assign('/login')
    }
    throw new ApiError(401, 'Authentication required')
  }
  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text) as unknown
    } catch {
      payload = text
    }
  }
  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String((payload as { detail?: unknown }).detail ?? response.statusText)
        : typeof payload === 'string'
          ? payload
          : response.statusText
    throw new ApiError(response.status, detail)
  }
  return payload as T
}

export const getStatus = () => api<Status>('/api/status')
export const getSummary = () => api<Summary>('/api/summary')
export const getPositions = () => api<Position[]>('/api/positions')
export const getPosition = (symbol: string) => api<PositionDetail>(`/api/positions/${encodeURIComponent(symbol)}`)
export const getTrades = (query: string) => api<TradeResponse>(`/api/trades?${query}`)
export const getTrade = (id: string) => api<TradeDetail>(`/api/trades/${encodeURIComponent(id)}`)
export const getEvents = (query: string) => api<EventResponse>(`/api/events?${query}`)
export const getLogs = (query: string) => api<{ items: LogLine[] }>(`/api/logs?${query}`)
export const getResearch = <T = unknown>(section: string, query = '') =>
  api<T>(`/api/research/${section}${query ? `?${query}` : ''}`)
export const getStats = (query: string) => api<Stats>(`/api/stats?${query}`)
export const getStrategies = () => api<Strategy[]>('/api/strategies')
export const getStrategySettings = (id: string) =>
  api<StrategySettings>(`/api/strategies/${encodeURIComponent(id)}/settings`)
export const getRisk = () => api<RiskResponse>('/api/risk')
