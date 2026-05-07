/**
 * WebSocket hook — connects to /api/v1/ws/alerts with JWT,
 * handles reconnect with exponential backoff, ping/pong keepalive.
 */
import { useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '@/store/auth'
import { useAlertsStore } from '@/store/alerts'
import type { WSMessage } from '@/types'

const WS_URL = (import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000') + '/api/v1/ws/alerts'
const MAX_RECONNECT_DELAY = 30_000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const reconnectDelay = useRef(1_000)
  const mountedRef = useRef(true)

  const accessToken = useAuthStore((s) => s.accessToken)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const { setWsConnected, setWsError, incrementUnread } = useAlertsStore()

  const connect = useCallback(() => {
    if (!accessToken || !isAuthenticated || !mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const url = `${WS_URL}?token=${encodeURIComponent(accessToken)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setWsConnected(true)
      setWsError(null)
      reconnectDelay.current = 1_000
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage
        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
        } else if (msg.type === 'new_alert') {
          incrementUnread()
          // Toast notification for critical alerts
          if (msg.severity === 'critical' || msg.severity === 'high') {
            import('react-hot-toast').then(({ default: toast }) => {
              toast.error(`🚨 ${msg.title}`, { duration: 6000 })
            })
          }
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      setWsError('WebSocket connection error')
    }

    ws.onclose = (event) => {
      if (!mountedRef.current) return
      setWsConnected(false)
      if (event.code !== 1000) {
        // Exponential backoff reconnect
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY)
          connect()
        }, reconnectDelay.current)
      }
    }
  }, [accessToken, isAuthenticated, setWsConnected, setWsError, incrementUnread])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close(1000, 'Component unmounted')
    }
  }, [connect])
}
