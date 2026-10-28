from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.schemas.otp import OtpRequestSchema, OtpVerifySchema, OtpResponseSchema
from app.services.otp_service import OtpService
from app.models.receipt import Bill, Receipt, Reminder
from app.models.user import User, Patient
from app.services.receipt_service import ReceiptService

router = APIRouter(prefix="/api/otp", tags=["Patient OTP Verification"])

@router.post("/request", response_model=OtpResponseSchema)
def request_patient_otp(payload: OtpRequestSchema, request: Request, db: Session = Depends(get_db)):
    """
    Request 6-digit OTP for patient verification.
    Applies rate limiting cooldown and salt-hash storage in MySQL healthslip_prod.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    success, msg, sandbox_otp, expires_in = OtpService.generate_otp(
        db=db,
        phone_number=payload.phone_number,
        receipt_number=payload.receipt_number,
        ip_address=client_ip
    )

    if not success:
        raise HTTPException(status_code=429, detail=msg)

    return OtpResponseSchema(
        success=True,
        message=msg,
        phone_number=payload.phone_number,
        receipt_number=payload.receipt_number,
        expires_in_seconds=expires_in,
        sandbox_otp=sandbox_otp
    )

@router.post("/verify", response_model=OtpResponseSchema)
def verify_patient_otp(payload: OtpVerifySchema, request: Request, db: Session = Depends(get_db)):
    """
    Verify submitted 6-digit OTP against salt-hashed DB record.
    Returns cryptographic access token for accessing medical health slips.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    success, msg, access_token = OtpService.verify_otp(
        db=db,
        phone_number=payload.phone_number,
        otp_code=payload.otp_code,
        receipt_number=payload.receipt_number,
        ip_address=client_ip
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return OtpResponseSchema(
        success=True,
        message=msg,
        phone_number=payload.phone_number,
        receipt_number=payload.receipt_number,
        access_token=access_token
    )

@router.get("/patient-slips")
def get_verified_patient_records(
    authorization: Optional[str] = Header(None, alias="X-Patient-Token"),
    token: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Fetch patient's health slips and active medication reminders after OTP verification.
    Requires verified access token in header 'X-Patient-Token' or query parameter 'token'.
    """
    active_token = authorization or token
    if not active_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Verification token required. Please verify via OTP.")

    otp_record = OtpService.validate_access_token(db, active_token)
    if not otp_record:
        raise HTTPException(status_code=403, detail="Invalid or expired verification session. Please verify via OTP again.")

    # Find patient by phone
    clean_phone = otp_record.identifier
    user = db.query(User).filter(User.phone_number == clean_phone).first()
    patient = user.patient if user else db.query(Patient).first()

    if not patient:
        return {"patient": None, "slips": [], "reminders": []}

    # Fetch patient's bills & receipts
    bills = db.query(Bill).filter(Bill.patient_id == patient.id).order_by(Bill.created_at.desc()).all()
    slips_data = []
    for b in bills:
        for r in b.receipts:
            slips_data.append(ReceiptService.build_slip_view_model(b, r))

    # Fetch reminders
    reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).order_by(Reminder.id.asc()).all()
    reminders_data = [
        {
            "id": r.id,
            "health_slip_id": bills[0].id if bills else 1,
            "medicine_name": r.medicine_name,
            "dosage": r.dosage,
            "timing_slot": r.timing_slot,
            "schedule_time": r.schedule_time,
            "instructions": r.instructions,
            "duration_days": 5,
            "is_done": r.is_done,
            "last_taken_at": r.created_at
        } for r in reminders
    ]

    return {
        "patient": {
            "id": patient.id,
            "full_name": patient.full_name,
            "phone": patient.phone,
            "age": patient.age,
            "gender": patient.gender,
            "blood_group": patient.blood_group
        },
        "slips": slips_data,
        "reminders": reminders_data
    }
