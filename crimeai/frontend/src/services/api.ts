/**
 * Axios API client — base configuration, interceptors, token refresh.
 * All API calls go through this client so auth is handled in one place.
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/auth'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const API_PREFIX = '/api/v1'

export const api = axios.create({
  baseURL: `${BASE_URL}${API_PREFIX}`,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor: attach JWT ──────────────────────────────────────────
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor: handle 401 / token refresh ─────────────────────────
let _isRefreshing = false
let _refreshQueue: Array<(token: string) => void> = []

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (error.response?.status === 401 && !original._retry) {
      if (_isRefreshing) {
        // Queue requests while refresh is in progress
        return new Promise((resolve) => {
          _refreshQueue.push((token: string) => {
            original.headers.Authorization = `Bearer ${token}`
            resolve(api(original))
          })
        })
      }

      original._retry = true
      _isRefreshing = true

      const refreshToken = useAuthStore.getState().refreshToken
      if (!refreshToken) {
        useAuthStore.getState().logout()
        return Promise.reject(error)
      }

      try {
        const { data } = await axios.post(`${BASE_URL}${API_PREFIX}/auth/refresh`, {
          refresh_token: refreshToken,
        })
        const newToken: string = data.access_token
        useAuthStore.getState().setAccessToken(newToken)

        _refreshQueue.forEach((cb) => cb(newToken))
        _refreshQueue = []
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      } catch {
        useAuthStore.getState().logout()
        return Promise.reject(error)
      } finally {
        _isRefreshing = false
      }
    }

    return Promise.reject(error)
  },
)

/** Extract a human-readable error message from an Axios error. */
export function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { message?: string; detail?: string } | undefined
    return data?.message ?? data?.detail ?? err.message ?? 'An error occurred'
  }
  if (err instanceof Error) return err.message
  return 'An unexpected error occurred'
}
