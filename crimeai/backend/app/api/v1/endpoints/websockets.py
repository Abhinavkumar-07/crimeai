"""
WebSocket endpoint for real-time alert streaming.
Clients subscribe and receive alert pushes as they are created.
Authentication via JWT passed as query parameter.
"""
import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError

from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.redis import get_redis_pool

router = APIRouter()
logger = get_logger(__name__)


class ConnectionManager:
    """Tracks active WebSocket connections per user."""

    def __init__(self) -> None:
        # {user_id: [WebSocket, ...]}
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        logger.info("ws_client_connected", user_id=user_id, total=self.total)

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        conns = self._connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(user_id, None)
        logger.info("ws_client_disconnected", user_id=user_id, total=self.total)

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected clients."""
        dead: list[tuple[str, WebSocket]] = []
        payload = json.dumps(message)
        for user_id, sockets in self._connections.items():
            for ws in sockets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((user_id, ws))
        for user_id, ws in dead:
            self.disconnect(ws, user_id)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        payload = json.dumps(message)
        for ws in self._connections.get(user_id, []):
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    @property
    def total(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Module-level singleton
manager = ConnectionManager()


@router.websocket("/alerts")
async def ws_alerts(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """
    WebSocket endpoint for real-time alerts.

    Connect: ws://host/api/v1/ws/alerts?token=<JWT>

    Messages sent to client:
      {"type": "connected", "user_id": "...", "message": "..."}
      {"type": "new_alert", "alert_id": "...", "severity": "...", "title": "..."}
      {"type": "ping"}

    Messages expected from client:
      {"type": "pong"}          — keepalive reply
      {"type": "mark_read", "alert_id": "..."}
    """
    # ── Authenticate ──────────────────────────────────────────────────────────
    try:
        payload = decode_token(token)
        user_id = payload["sub"]
        user_role = payload["role"]
    except (JWTError, KeyError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id)

    # Send welcome frame
    await websocket.send_text(json.dumps({
        "type": "connected",
        "user_id": user_id,
        "role": user_role,
        "message": "Connected to CrimeAI real-time alert stream",
    }))

    # ── Subscribe to Redis pub/sub ─────────────────────────────────────────────
    redis = await get_redis_pool()
    pubsub = redis.pubsub()
    await pubsub.subscribe("alerts:broadcast")

    # Run two concurrent tasks: receive from Redis, receive from client
    async def _redis_listener() -> None:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    data = json.loads(msg["data"])
                    await websocket.send_text(json.dumps(data))
                except Exception as exc:
                    logger.warning("ws_redis_send_failed", error=str(exc))

    async def _client_listener() -> None:
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "pong":
                    pass  # keepalive acknowledged
            except WebSocketDisconnect:
                return
            except Exception:
                return

    # Ping every 30 seconds to keep the connection alive through proxies
    async def _ping_loop() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                return

    try:
        await asyncio.gather(
            _redis_listener(),
            _client_listener(),
            _ping_loop(),
            return_exceptions=True,
        )
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe("alerts:broadcast")
        await pubsub.aclose()
        manager.disconnect(websocket, user_id)
