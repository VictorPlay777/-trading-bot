import { format } from 'date-fns'

export function numberValue(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function fmtUsd(value: unknown): string {
  const amount = numberValue(value)
  return `${amount < 0 ? '−' : amount > 0 ? '+' : ''}$${Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
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
  const seconds = numberValue(value)
  if (!seconds) return 'now'
  return `${fmtDuration(seconds)} ago`
}

export function toneFor(value: unknown): 'profit' | 'loss' | 'muted' {
  const amount = numberValue(value)
  return amount > 0 ? 'profit' : amount < 0 ? 'loss' : 'muted'
}
