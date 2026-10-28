import json
import logging
import datetime
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("healthslip.websocket")

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WebSocket] Client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WebSocket] Client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast JSON message to all active WebSocket clients"""
        if not self.active_connections:
            return

        payload = json.dumps({
            "event": event_type,
            "data": data,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"[WebSocket] Error broadcasting to client: {e}")
                disconnected.append(connection)

        for dead_conn in disconnected:
            self.disconnect(dead_conn)

    def sync_broadcast(self, event_type: str, data: Dict[str, Any]):
        """Safe non-blocking broadcast callable from standard synchronous FastAPI routes"""
        try:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(self.broadcast(event_type, data))
            except RuntimeError:
                # No running loop in this thread, try stored loop or run in background
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), self._loop)
                else:
                    new_loop = asyncio.new_event_loop()
                    new_loop.run_until_complete(self.broadcast(event_type, data))
                    new_loop.close()
        except Exception as e:
            logger.warning(f"[WebSocket] sync_broadcast warning: {e}")

ws_manager = WebSocketManager()

