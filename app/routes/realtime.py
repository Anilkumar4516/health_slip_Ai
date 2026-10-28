import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket_manager import ws_manager

logger = logging.getLogger("healthslip.realtime")
router = APIRouter(tags=["Real-Time WebSockets"])

@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    Real-Time WebSocket channel for HealthSlip AI.
    Streams live prescription issuances, pharmacy dispense updates,
    low-stock alerts, and medication reminder notifications.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial confirmation handshake
        await websocket.send_text(json.dumps({
            "event": "CONNECTED",
            "data": {
                "message": "Connected to HealthSlip AI Real-Time WebSocket Hub",
                "features": ["live_prescriptions", "dispense_lock", "stock_alerts", "audio_dosage"]
            }
        }))

        while True:
            # Keep connection alive & handle incoming pings or client requests
            raw_data = await websocket.receive_text()
            try:
                payload = json.loads(raw_data)
                event = payload.get("event")
                if event == "PING":
                    await websocket.send_text(json.dumps({"event": "PONG"}))
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
        "active_clients": len(ws_manager.active_connections)
    }
