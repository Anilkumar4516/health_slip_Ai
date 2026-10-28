from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, get_db_status
from app.models.receipt import Receipt, Bill, Reminder
from app.models.verification import AuthOtp, AuditEvent
from app.models.user import Patient

router = APIRouter(prefix="/api/stats", tags=["Analytics & System"])

@router.get("")
def get_clinic_metrics(db: Session = Depends(get_db)):
    """Fetch analytics for clinic dashboard from healthslip_prod"""
    total_slips = db.query(Receipt).count()
    cents_sum = db.query(func.sum(Receipt.amount_paid_cents)).scalar() or 0
    total_revenue = round(float(cents_sum) / 100.0, 2)
    total_patients = db.query(Patient).count()
    
    total_otps = db.query(AuthOtp).count()
    verified_otps = db.query(AuthOtp).filter(AuthOtp.is_consumed == True).count()
    otp_success_rate = round((verified_otps / total_otps * 100), 1) if total_otps > 0 else 100.0

    total_reminders = db.query(Reminder).count()
    done_reminders = db.query(Reminder).filter((Reminder.status == 'SENT') | (Reminder.status == 'DISMISSED')).count()
    adherence_rate = round((done_reminders / total_reminders * 100), 1) if total_reminders > 0 else 100.0

    recent_audits = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10).all()
    audit_data = [
        {
            "id": a.id,
            "action": a.action,
            "actor_type": "AUDIT",
            "identifier": a.resource_id,
            "status": "LOGGED",
            "details": f"{a.resource_type} ({a.action})",
            "created_at": a.created_at.strftime("%H:%M:%S")
        } for a in recent_audits
    ]

    return {
        "total_slips": total_slips,
        "total_revenue": total_revenue,
        "total_patients": total_patients,
        "total_otps_sent": total_otps,
        "otp_success_rate": otp_success_rate,
        "total_reminders": total_reminders,
        "adherence_rate": adherence_rate,
        "db_status": get_db_status(),
        "recent_audits": audit_data
    }

@router.get("/db-status")
def check_db_health():
    """Check database status and connectivity"""
    return get_db_status()
