import { api } from './api'
import type { AuthTokens, User } from '@/types'

export const authApi = {
  login: (email: string, password: string) =>
    api.post<AuthTokens>('/auth/login', { email, password }).then((r) => r.data),

  register: (payload: {
    email: string; password: string; full_name: string;
    badge_number?: string; department?: string
  }) => api.post('/auth/register', payload).then((r) => r.data),

  refresh: (refresh_token: string) =>
    api.post<{ access_token: string; token_type: string; expires_in: number }>(
      '/auth/refresh', { refresh_token }
    ).then((r) => r.data),

  me: () =>
    api.get<User>('/users/me').then((r) => r.data),
}
