import os
import json
import logging
import datetime
import asyncio
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
from fastapi import WebSocket
from app.config import settings

logger = logging.getLogger("healthslip.websocket")

class WebSocketManager:
    """
    Production-grade WebSocket hub supporting:
    - Multi-worker scalability via Redis Pub/Sub (fallback to local in-memory event bus)
    - Role and Room-based isolation:
        * store_rooms: isolated per pharmacy store_id
        * patient_rooms: isolated per patient phone
        * staff_sockets: clinical staff (doctors/admins) receiving relevant clinic alerts
    - Heartbeat ping/pong and graceful disconnect cleanup
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connections_meta: Dict[WebSocket, Dict[str, Any]] = {}
        self.store_rooms: Dict[int, Set[WebSocket]] = defaultdict(set)
        self.patient_rooms: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.staff_sockets: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._redis_client = None
        self._redis_sub_task = None
        self._redis_channel = "healthslip:realtime_channel"

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def init_redis_if_available(self):
        """Initialize Redis Pub/Sub connection if enabled in settings"""
        if settings.REDIS_ENABLED or os.getenv("REDIS_URL"):
            try:
                import redis.asyncio as aioredis
                redis_url = os.getenv("REDIS_URL") or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
                self._redis_client = aioredis.from_url(redis_url, decode_responses=True)
                # Test ping
                await self._redis_client.ping()
                logger.info(f"[WebSocket] Connected to Redis Pub/Sub backend at {redis_url}")
                # Start listener task
                self._redis_sub_task = asyncio.create_task(self._redis_listener())
            except Exception as e:
                logger.warning(f"[WebSocket] Redis unavailable ({e}). Falling back to in-memory event bus.")
                self._redis_client = None

    async def _redis_listener(self):
        """Background coroutine listening to Redis Pub/Sub channel for multi-worker fanout"""
        try:
            pubsub = self._redis_client.pubsub()
            await pubsub.subscribe(self._redis_channel)
            async for message in pubsub.listen():
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        event = data.get("event")
                        event_data = data.get("data", {})
                        target_store_id = data.get("store_id")
                        target_patient_phone = data.get("patient_phone")
                        await self._local_broadcast(
                            event_type=event,
                            data=event_data,
                            target_store_id=target_store_id,
                            target_patient_phone=target_patient_phone
                        )
                    except Exception as err:
                        logger.error(f"[WebSocket] Error parsing Redis event: {err}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[WebSocket] Redis listener interrupted: {e}")

    async def connect(
        self,
        websocket: WebSocket,
        user_id: Optional[int] = None,
        role: Optional[str] = None,
        store_id: Optional[int] = None,
        patient_phone: Optional[str] = None
    ):
        await websocket.accept()
        self.active_connections.append(websocket)
        meta = {
            "user_id": user_id,
            "role": role,
            "store_id": store_id,
            "patient_phone": patient_phone,
            "connected_at": datetime.datetime.utcnow().isoformat()
        }
        self.connections_meta[websocket] = meta

        # Add to store room
        if store_id:
            self.store_rooms[store_id].add(websocket)

        # Add to patient room
        if patient_phone:
            clean_phone = patient_phone.strip().replace(" ", "").replace("-", "")
            self.patient_rooms[clean_phone].add(websocket)

        # Add to clinical staff room
        if role in ("DOCTOR", "ADMIN"):
            self.staff_sockets.add(websocket)

        logger.info(
            f"[WebSocket] Client connected: user={user_id}, role={role}, store={store_id}, "
            f"phone={patient_phone}. Total active: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        meta = self.connections_meta.pop(websocket, None)
        if meta:
            store_id = meta.get("store_id")
            if store_id and store_id in self.store_rooms:
                self.store_rooms[store_id].discard(websocket)
            patient_phone = meta.get("patient_phone")
            if patient_phone:
                clean_phone = patient_phone.strip().replace(" ", "").replace("-", "")
                if clean_phone in self.patient_rooms:
                    self.patient_rooms[clean_phone].discard(websocket)
        self.staff_sockets.discard(websocket)
        logger.info(f"[WebSocket] Client disconnected. Total active: {len(self.active_connections)}")

    async def _local_broadcast(
        self,
        event_type: str,
        data: Dict[str, Any],
        target_store_id: Optional[int] = None,
        target_patient_phone: Optional[str] = None
    ):
        """Dispatch message to local connected sockets matching target store or patient rooms"""
        if not self.active_connections:
            return

        payload = json.dumps({
            "event": event_type,
            "data": data,
            "store_id": target_store_id,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        recipients: Set[WebSocket] = set()

        if target_store_id is not None:
            # Deliver to pharmacists in this store + clinical staff
            recipients.update(self.store_rooms.get(target_store_id, set()))
            recipients.update(self.staff_sockets)
        elif target_patient_phone is not None:
            # Deliver to this specific patient + clinical staff
            clean_phone = target_patient_phone.strip().replace(" ", "").replace("-", "")
            recipients.update(self.patient_rooms.get(clean_phone, set()))
            recipients.update(self.staff_sockets)
        else:
            # Global broadcast to all clients
            recipients.update(self.active_connections)

        disconnected = []
        for connection in recipients:
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"[WebSocket] Error sending message: {e}")
                disconnected.append(connection)

        for dead_conn in disconnected:
            self.disconnect(dead_conn)

    async def broadcast(
        self,
        event_type: str,
        data: Dict[str, Any],
        target_store_id: Optional[int] = None,
        target_patient_phone: Optional[str] = None
    ):
        """Broadcast message either across Redis cluster or locally if Redis is disabled"""
        if self._redis_client:
            try:
                msg = json.dumps({
                    "event": event_type,
                    "data": data,
                    "store_id": target_store_id,
                    "patient_phone": target_patient_phone,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                })
                await self._redis_client.publish(self._redis_channel, msg)
                return
            except Exception as err:
                logger.warning(f"[WebSocket] Redis publish failed ({err}), falling back to local broadcast")

        await self._local_broadcast(
            event_type=event_type,
            data=data,
            target_store_id=target_store_id,
            target_patient_phone=target_patient_phone
        )

    def sync_broadcast(
        self,
        event_type: str,
        data: Dict[str, Any],
        target_store_id: Optional[int] = None,
        target_patient_phone: Optional[str] = None
    ):
        """Safe non-blocking broadcast callable from standard synchronous FastAPI routes"""
        try:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(
                    self.broadcast(event_type, data, target_store_id, target_patient_phone)
                )
            except RuntimeError:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.broadcast(event_type, data, target_store_id, target_patient_phone),
                        self._loop
                    )
                else:
                    new_loop = asyncio.new_event_loop()
                    new_loop.run_until_complete(
                        self.broadcast(event_type, data, target_store_id, target_patient_phone)
                    )
                    new_loop.close()
        except Exception as e:
            logger.warning(f"[WebSocket] sync_broadcast warning: {e}")

ws_manager = WebSocketManager()
