import json
import logging
import datetime
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.websocket_manager import ws_manager
from app.database import SessionLocal
from app.services.auth_service import AuthService

logger = logging.getLogger("healthslip.realtime")
router = APIRouter(tags=["Real-Time WebSockets"])

@router.websocket("/ws/live")
async def websocket_live_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    store_id: Optional[int] = Query(None),
    patient_phone: Optional[str] = Query(None)
):
    """
    Authenticated Real-Time WebSocket channel for HealthSlip AI.
    Streams live prescription issuances, pharmacy dispense updates,
    low-stock alerts, and medication reminder notifications.
    Room isolation:
    - store_id: pharmacy store connections only receive events for their store
    - patient_phone: patient connections only receive events for their phone
    - doctors/admins: receive clinic-wide updates
    """
    user_id = None
    role = None
    resolved_store_id = store_id
    resolved_patient_phone = patient_phone

    if token:
        db = SessionLocal()
        try:
            user = AuthService.validate_token(db, token)
            if user:
                user_id = user.id
                user_roles = [ur.role.code for ur in user.roles if ur.role]
                if "ADMIN" in user_roles:
                    role = "ADMIN"
                elif "DOCTOR" in user_roles:
                    role = "DOCTOR"
                elif "PHARMACIST" in user_roles:
                    role = "PHARMACIST"
                    if user.store_id:
                        resolved_store_id = user.store_id
                elif "PATIENT" in user_roles:
                    role = "PATIENT"
                    if user.phone_number:
                        resolved_patient_phone = user.phone_number
            else:
                # Try decoding JWT without active session (e.g. stateless access token)
                payload = AuthService.decode_jwt_token(token)
                if payload:
                    user_id = payload.get("sub")
                    role = payload.get("role")
                    if payload.get("store_id"):
                        resolved_store_id = payload.get("store_id")
                    if payload.get("phone"):
                        resolved_patient_phone = payload.get("phone")
        except Exception as e:
            logger.warning(f"[WebSocket Auth] Token validation warning: {e}")
        finally:
            db.close()

    await ws_manager.connect(
        websocket=websocket,
        user_id=user_id,
        role=role,
        store_id=resolved_store_id,
        patient_phone=resolved_patient_phone
    )

    try:
        # Initial confirmation handshake with assigned room details
        await websocket.send_text(json.dumps({
            "event": "CONNECTED",
            "data": {
                "message": "Connected to HealthSlip AI Real-Time WebSocket Hub",
                "role": role or "GUEST",
                "store_id": resolved_store_id,
                "patient_phone": resolved_patient_phone,
                "server_time": datetime.datetime.utcnow().isoformat()
            }
        }))

        while True:
            raw_data = await websocket.receive_text()
            try:
                payload = json.loads(raw_data)
                event = payload.get("event")
                if event == "PING":
                    await websocket.send_text(json.dumps({
                        "event": "PONG",
                        "timestamp": datetime.datetime.utcnow().isoformat()
                    }))
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"[WebSocket] Exception: {e}")
        ws_manager.disconnect(websocket)

@router.get("/api/realtime/status")
def get_realtime_status():
    """Check number of connected real-time devices/counters"""
    return {
        "status": "online",
        "active_clients": len(ws_manager.active_connections),
        "store_rooms_count": len(ws_manager.store_rooms),
        "patient_rooms_count": len(ws_manager.patient_rooms),
        "staff_clients": len(ws_manager.staff_sockets)
    }
