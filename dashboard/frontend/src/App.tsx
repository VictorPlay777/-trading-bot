import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api } from './api'
import { Layout, Spinner, Toasts } from './components'
import { LiveProvider } from './live'
import { Dashboard, EventsPage, Login, PositionsPage, RiskPage, StatisticsPage, StrategiesPage, StrategySettingsPage, TradesPage } from './pages'
import './App.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 5000 } },
})

const ToastContext = createContext<(message: string) => void>(() => undefined)
export const useToast = () => useContext(ToastContext)

function Protected() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<string[]>([])
  const auth = useQuery({ queryKey: ['auth'], queryFn: () => api<{ user: string }>('/api/auth/me') })
  useEffect(() => {
    if (auth.error) navigate('/login', { replace: true })
  }, [auth.error, navigate])
  const toast = (message: string) => setMessages((existing) => [...existing.slice(-3), message])
  const logout = async () => {
    await api('/api/auth/logout', { method: 'POST' })
    navigate('/login', { replace: true })
  }
  if (auth.isPending) return <div className="screen-center"><Spinner /></div>
  if (auth.error) return null
  return (
    <ToastContext.Provider value={toast}>
      <LiveProvider>
        <Layout onLogout={() => void logout()}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/positions" element={<PositionsPage />} />
            <Route path="/strategies" element={<StrategiesPage />} />
            <Route path="/strategies/:strategyId/settings" element={<StrategySettingsPage />} />
            <Route path="/risk" element={<RiskPage />} />
            <Route path="/statistics" element={<StatisticsPage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </LiveProvider>
      <Toasts messages={messages} onDismiss={(message) => setMessages((existing) => existing.filter((item) => item !== message))} />
    </ToastContext.Provider>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<Protected />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export function FieldLabel({ children, hint }: { children: ReactNode; hint?: string }) {
  return <label className="field"><span>{children}</span>{hint && <small>{hint}</small>}</label>
}
