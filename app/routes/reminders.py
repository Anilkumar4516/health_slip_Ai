import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.receipt import Reminder
from app.schemas.receipt import MedicationReminderResponse

router = APIRouter(prefix="/api/reminders", tags=["Medication Reminders"])

@router.get("", response_model=List[MedicationReminderResponse])
def get_reminders(
    patient_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Fetch active medication reminders from MySQL healthslip_prod"""
    query = db.query(Reminder)
    if patient_id:
        query = query.filter(Reminder.patient_id == patient_id)

    records = query.order_by(Reminder.id.asc()).all()
    results = []
    for r in records:
        results.append(MedicationReminderResponse(
            id=r.id,
            health_slip_id=1,
            patient_id=r.patient_id,
            medicine_name=r.medicine_name,
            dosage=r.dosage,
            timing_slot=r.timing_slot,
            schedule_time=r.schedule_time,
            instructions=r.instructions,
            duration_days=5,
            is_done=r.is_done,
            created_at=r.created_at
        ))
    return results

@router.post("/{reminder_id}/toggle", response_model=MedicationReminderResponse)
def toggle_reminder_status(reminder_id: int, db: Session = Depends(get_db)):
    """
    Toggle adherence status for a dose (DONE vs PENDING).
    Matches the interactive 'DONE' button on the mobile reminder card.
    """
    rem = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder record not found.")

    rem.status = 'DISMISSED' if rem.status == 'PENDING' else 'PENDING'
    db.commit()
    db.refresh(rem)

    # Real-time WebSocket broadcast of dose adherence
    try:
        from app.services.websocket_manager import ws_manager
        ws_manager.sync_broadcast("REMINDER_TOGGLED", {
            "reminder_id": rem.id,
            "medicine_name": rem.medicine_name,
            "is_done": rem.is_done,
            "status": rem.status
        })
    except Exception:
        pass

    return MedicationReminderResponse(
        id=rem.id,
        health_slip_id=1,
        patient_id=rem.patient_id,
        medicine_name=rem.medicine_name,
        dosage=rem.dosage,
        timing_slot=rem.timing_slot,
        schedule_time=rem.schedule_time,
        instructions=rem.instructions,
        duration_days=5,
        is_done=rem.is_done,
        created_at=rem.created_at
    )
