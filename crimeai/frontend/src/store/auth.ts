/**
 * Auth Zustand store — persists tokens in localStorage,
 * provides login/logout actions, and role-check helpers.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, UserRole } from '@/types'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  isAuthenticated: boolean

  // Actions
  login: (tokens: { access_token: string; refresh_token: string; user_id: string; role: UserRole; full_name: string }) => void
  logout: () => void
  setAccessToken: (token: string) => void
  setUser: (user: User) => void

  // Role helpers
  hasRole: (minimum: UserRole) => boolean
  isAdmin: () => boolean
  isPolice: () => boolean
  isAnalyst: () => boolean
}

const ROLE_RANK: Record<UserRole, number> = {
  readonly: 0, analyst: 1, police: 2, admin: 3,
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      login: ({ access_token, refresh_token, user_id, role, full_name }) => {
        set({
          accessToken: access_token,
          refreshToken: refresh_token,
          isAuthenticated: true,
          user: { id: user_id, email: '', full_name, role, badge_number: null, department: null },
        })
      },

      logout: () => {
        set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false })
      },

      setAccessToken: (token) => set({ accessToken: token }),
      setUser: (user) => set({ user }),

      hasRole: (minimum) => {
        const role = get().user?.role ?? 'readonly'
        return ROLE_RANK[role] >= ROLE_RANK[minimum]
      },
      isAdmin: () => get().user?.role === 'admin',
      isPolice: () => (ROLE_RANK[get().user?.role ?? 'readonly'] ?? 0) >= ROLE_RANK.police,
      isAnalyst: () => (ROLE_RANK[get().user?.role ?? 'readonly'] ?? 0) >= ROLE_RANK.analyst,
    }),
    {
      name: 'crimeai-auth',
      partialize: (s) => ({ accessToken: s.accessToken, refreshToken: s.refreshToken, user: s.user, isAuthenticated: s.isAuthenticated }),
    }
  )
)
