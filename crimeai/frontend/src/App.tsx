import { Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import ProtectedRoute from '@/components/ui/ProtectedRoute'
import AppLayout from '@/components/layout/AppLayout'
import LoginPage from '@/pages/auth/LoginPage'

// Lazy-load heavy pages
const DashboardPage   = lazy(() => import('@/pages/dashboard/DashboardPage'))
const CrimeMapPage    = lazy(() => import('@/pages/crimes/CrimeMapPage'))
const CrimeListPage   = lazy(() => import('@/pages/crimes/CrimeListPage'))
const FIRPage         = lazy(() => import('@/pages/fir/FIRPage'))
const AlertsPage      = lazy(() => import('@/pages/alerts/AlertsPage'))
const PatrolPage      = lazy(() => import('@/pages/patrol/PatrolPage'))
const SimulationPage  = lazy(() => import('@/pages/simulation/SimulationPage'))
const AdminPage       = lazy(() => import('@/pages/admin/AdminPage'))

function SuspenseLayout(props: { title?: string; subtitle?: string }) {
  return (
    <AppLayout {...props}>
      <Suspense fallback={<PageLoader />}>
        <></>
      </Suspense>
    </AppLayout>
  )
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      {/* Protected: all authenticated users */}
      <Route element={<ProtectedRoute minimumRole="readonly" />}>
        <Route element={<AppLayout title="Dashboard" subtitle="Real-time crime intelligence" />}>
          <Route path="/dashboard" element={<Suspense fallback={<PageLoader />}><DashboardPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Alerts" subtitle="Active notifications & warnings" />}>
          <Route path="/alerts" element={<Suspense fallback={<PageLoader />}><AlertsPage /></Suspense>} />
        </Route>
      </Route>

      {/* Protected: police and above */}
      <Route element={<ProtectedRoute minimumRole="police" />}>
        <Route element={<AppLayout title="Crime Map" subtitle="Geospatial crime intelligence" />}>
          <Route path="/crimes" element={<Suspense fallback={<PageLoader />}><CrimeMapPage /></Suspense>} />
          <Route path="/crimes/list" element={<Suspense fallback={<PageLoader />}><CrimeListPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="FIR Analysis" subtitle="NLP-powered FIR processing" />}>
          <Route path="/fir" element={<Suspense fallback={<PageLoader />}><FIRPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Patrol Optimizer" subtitle="AI-driven patrol route planning" />}>
          <Route path="/patrol" element={<Suspense fallback={<PageLoader />}><PatrolPage /></Suspense>} />
        </Route>
      </Route>

      {/* Protected: analyst and above */}
      <Route element={<ProtectedRoute minimumRole="analyst" />}>
        <Route element={<AppLayout title="What-If Simulation" subtitle="Monte Carlo crime intervention modelling" />}>
          <Route path="/simulation" element={<Suspense fallback={<PageLoader />}><SimulationPage /></Suspense>} />
        </Route>
      </Route>

      {/* Protected: admin only */}
      <Route element={<ProtectedRoute minimumRole="admin" />}>
        <Route element={<AppLayout title="Admin Panel" subtitle="System administration & user management" />}>
          <Route path="/admin" element={<Suspense fallback={<PageLoader />}><AdminPage /></Suspense>} />
        </Route>
      </Route>

      {/* 404 fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
