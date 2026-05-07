import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import type { UserRole } from '@/types'

interface ProtectedRouteProps {
  minimumRole?: UserRole
}

const ROLE_RANK: Record<UserRole, number> = {
  readonly: 0, analyst: 1, police: 2, admin: 3,
}

export default function ProtectedRoute({ minimumRole = 'readonly' }: ProtectedRouteProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)

  if (!isAuthenticated) return <Navigate to="/login" replace />

  if (minimumRole && user) {
    const userRank = ROLE_RANK[user.role] ?? 0
    const requiredRank = ROLE_RANK[minimumRole] ?? 0
    if (userRank < requiredRank) return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
