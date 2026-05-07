import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AlertPanel from '../alerts/AlertPanel'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useUIStore } from '@/store/ui'
import { cn } from '@/utils'

interface AppLayoutProps {
  title?: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function AppLayout({ title = 'CrimeAI', subtitle, actions }: AppLayoutProps) {
  // Start WebSocket connection for real-time alerts
  useWebSocket()

  const alertPanelOpen = useUIStore((s) => s.alertPanelOpen)

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar title={title} subtitle={subtitle} actions={actions} />

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* Slide-in alert panel */}
      <AlertPanel open={alertPanelOpen} />
    </div>
  )
}
