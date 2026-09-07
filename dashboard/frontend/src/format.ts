import { format } from 'date-fns'

export function numberValue(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function fmtUsd(value: unknown, showSign = true): string {
  if (value === null || value === undefined || value === '') return '—'
  const amount = numberValue(value)
  const sign = showSign && amount < 0 ? '−' : showSign && amount > 0 ? '+' : ''
  return `${sign}$${Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function fmtPct(value: unknown, digits = 2): string {
  const amount = numberValue(value)
  return `${amount < 0 ? '−' : ''}${Math.abs(amount).toFixed(digits)}%`
}

export function fmtPrice(value: unknown): string {
  const amount = numberValue(value)
  const digits = amount >= 100 ? 2 : amount >= 1 ? 4 : 6
  return amount.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtDuration(seconds: unknown): string {
  if (seconds === null || seconds === undefined || seconds === '') return '—'
  const total = Math.max(0, Math.round(numberValue(seconds)))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  if (minutes) return `${minutes}m ${secs}s`
  return `${secs}s`
}

export function fmtTs(value: unknown): string {
  const timestamp = numberValue(value)
  if (!timestamp) return '—'
  return format(new Date(timestamp * 1000), 'dd MMM HH:mm:ss')
}

export function fmtAge(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const seconds = numberValue(value)
  if (!seconds) return 'now'
  return `${fmtDuration(seconds)} ago`
}

export function fmtQty(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const amount = numberValue(value)
  return amount.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

export function fmtChartTs(value: unknown): string {
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return format(new Date(`${value}T00:00:00Z`), 'dd MMM')
  }
  const timestamp = numberValue(value)
  return timestamp ? format(new Date(timestamp * 1000), 'dd MMM HH:mm') : '—'
}

export function periodParams(period: string, startDate: string, endDate: string): Record<string, string> {
  if (period !== 'custom') return { period }
  const params: Record<string, string> = { period }
  if (startDate) params.start = String(Date.parse(`${startDate}T00:00:00Z`) / 1000)
  if (endDate) params.end = String(Date.parse(`${endDate}T23:59:59.999Z`) / 1000)
  return params
}

export function toneFor(value: unknown): 'profit' | 'loss' | 'muted' {
  const amount = numberValue(value)
  return amount > 0 ? 'profit' : amount < 0 ? 'loss' : 'muted'
}
