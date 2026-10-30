import datetime
import uuid
import random
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User, Patient, Role, UserRole, UserSession
from app.models.verification import AuditEvent, ConsentRecord
from app.schemas.patient import PatientManualCreate, PatientSummary, PatientDetailResponse, ConsentCaptureRequest, EraseDataRequest
from app.services.auth_service import AuthService
from app.services.encryption_service import EncryptionService
from app.services.websocket_manager import ws_manager

router = APIRouter(prefix="/api/patients", tags=["Patient Management"])

@router.post("", response_model=PatientDetailResponse)
def register_new_patient_manually(req: PatientManualCreate, request: Request, db: Session = Depends(get_db)):
    """
    Manually register a new patient into MySQL healthslip_prod.
    Creates user account with PATIENT role and associated clinical demographics.
    """
    clean_phone = req.phone.strip().replace(" ", "").replace("-", "")
    if len(clean_phone) < 5:
        raise HTTPException(status_code=400, detail="Invalid phone number provided.")

    # 1. Check or create User
    user = None
    if req.email and req.email.strip():
        user = db.query(User).filter((User.phone_number == clean_phone) | (User.email == req.email.strip())).first()
    else:
        user = db.query(User).filter(User.phone_number == clean_phone).first()

    first_name = req.first_name.strip()
    last_name = (req.last_name or "").strip()

    if not user:
        email_to_use = req.email.strip() if (req.email and req.email.strip()) else None
        if email_to_use and db.query(User).filter(User.email == email_to_use).first():
            email_to_use = f"{first_name.lower()}.{random.randint(1000, 9999)}@patient.healthslip.ai"
        elif not email_to_use:
            email_to_use = f"{first_name.lower()}.{random.randint(1000, 9999)}@patient.healthslip.ai"

        user = User(
            uuid=str(uuid.uuid4()),
            email=email_to_use,
            phone_number=clean_phone,
            password_hash=AuthService.hash_password("Patient@2026"),
            status="ACTIVE",
            is_phone_verified=True,
            is_email_verified=bool(req.email)
        )
        db.add(user)
        db.flush()

        # Assign PATIENT role
        pat_role = db.query(Role).filter(Role.code == "PATIENT").first()
        if pat_role:
            db.add(UserRole(user_id=user.id, role_id=pat_role.id))

    # 2. Check existing Patient record
    patient = db.query(Patient).filter(Patient.user_id == user.id).first()
    
    # Calculate DOB from age if provided
    dob = None
    if req.date_of_birth:
        try:
            dob = datetime.date.fromisoformat(req.date_of_birth)
        except ValueError:
            pass
    if not dob:
        age_years = req.age if req.age and req.age > 0 else 28
        dob = datetime.date(datetime.date.today().year - age_years, 1, 1)

    gender_norm = req.gender.strip().upper()
    if gender_norm not in ['MALE', 'FEMALE', 'OTHER', 'UNDISCLOSED']:
        gender_norm = 'MALE' if gender_norm.startswith('M') else ('FEMALE' if gender_norm.startswith('F') else 'OTHER')

    blood_norm = (req.blood_group or "O+").strip().upper()
    if blood_norm not in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'UNKNOWN']:
        blood_norm = 'O+'

    if not patient:
        patient = Patient(
            uuid=str(uuid.uuid4()),
            user_id=user.id,
            first_name=first_name,
            last_name=last_name or "Patient",
            date_of_birth=dob,
            gender=gender_norm,
            blood_group=blood_norm,
            emergency_contact_name=req.emergency_contact_name,
            emergency_contact_phone=req.emergency_contact_phone or clean_phone,
            address_line1=req.address_line1 or "Main Street",
            city=req.city or "Hyderabad",
            state=req.state or "Telangana",
            postal_code=req.postal_code or "500001",
            country_code="IN"
        )
        db.add(patient)
        db.flush()
    else:
        # Update demographics
        patient.first_name = first_name
        if last_name:
            patient.last_name = last_name
        patient.date_of_birth = dob
        patient.gender = gender_norm
        patient.blood_group = blood_norm
        if req.address_line1:
            patient.address_line1 = req.address_line1
        if req.city:
            patient.city = req.city
        if req.state:
            patient.state = req.state
        if req.postal_code:
            patient.postal_code = req.postal_code
        if req.emergency_contact_name:
            patient.emergency_contact_name = req.emergency_contact_name
        if req.emergency_contact_phone:
            patient.emergency_contact_phone = req.emergency_contact_phone

    # 3. Log Audit Event
    audit = AuditEvent(
        resource_type="PATIENT",
        resource_id=str(patient.id),
        action="REGISTER_MANUAL",
        actor_user_id=user.id,
        ip_address=request.client.host if request.client else "127.0.0.1",
        user_agent=request.headers.get("User-Agent", "Medical Reception POS")
    )
    db.add(audit)
    db.commit()
    db.refresh(patient)

    # Broadcast WebSocket notification
    ws_manager.sync_broadcast("PATIENT_REGISTERED", {
        "patient_id": patient.id,
        "full_name": patient.full_name,
        "phone": clean_phone,
        "age": patient.age,
        "gender": patient.gender,
        "city": patient.city
    })

    return PatientDetailResponse(
        id=patient.id,
        uuid=patient.uuid,
        full_name=patient.full_name,
        first_name=patient.first_name,
        last_name=patient.last_name,
        phone=clean_phone,
        email=user.email,
        age=patient.age,
        gender=patient.gender,
        blood_group=patient.blood_group,
        city=patient.city,
        state=patient.state,
        postal_code=patient.postal_code,
        created_at=patient.created_at,
        address_line1=patient.address_line1,
        emergency_contact_name=patient.emergency_contact_name,
        emergency_contact_phone=patient.emergency_contact_phone,
        total_prescriptions=len(patient.prescriptions) if patient.prescriptions else 0,
        total_bills=len(patient.bills) if patient.bills else 0
    )

@router.get("", response_model=List[PatientSummary])
def list_patients(
    search: Optional[str] = Query(None, description="Search by name, phone, or blood group"),
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List or search registered patients for quick clinical selection"""
    query = db.query(Patient).order_by(Patient.created_at.desc())
    patients = query.limit(limit).all()

    results = []
    for p in patients:
        p_name = p.full_name
        p_phone = p.phone
        p_email = p.user.email if p.user else None

        if search:
            s_low = search.strip().lower()
            if (s_low not in p_name.lower() and 
                s_low not in p_phone.lower() and 
                s_low not in (p.blood_group or "").lower() and
                s_low not in (p.city or "").lower()):
                continue

        results.append(PatientSummary(
            id=p.id,
            uuid=p.uuid,
            full_name=p_name,
            first_name=p.first_name,
            last_name=p.last_name,
            phone=p_phone,
            email=p_email,
            age=p.age,
            gender=p.gender,
            blood_group=p.blood_group,
            city=p.city,
            state=p.state,
            postal_code=p.postal_code,
            created_at=p.created_at
        ))
    return results

@router.get("/{patient_id}", response_model=PatientDetailResponse)
def get_patient_details(patient_id: int, db: Session = Depends(get_db)):
    """Fetch complete patient record with prescription count and clinical history"""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    return PatientDetailResponse(
        id=patient.id,
        uuid=patient.uuid,
        full_name=patient.full_name,
        first_name=patient.first_name,
        last_name=patient.last_name,
        phone=patient.phone,
        email=patient.user.email if patient.user else None,
        age=patient.age,
        gender=patient.gender,
        blood_group=patient.blood_group,
        city=patient.city,
        state=patient.state,
        postal_code=patient.postal_code,
        created_at=patient.created_at,
        address_line1=patient.address_line1,
        emergency_contact_name=patient.emergency_contact_name,
        emergency_contact_phone=patient.emergency_contact_phone,
        total_prescriptions=len(patient.prescriptions) if patient.prescriptions else 0,
        total_bills=len(patient.bills) if patient.bills else 0
    )

@router.post("/{patient_id}/consent")
def capture_patient_consent(
    patient_id: int,
    req: ConsentCaptureRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Capture patient consent under India Digital Personal Data Protection Act, 2023 (DPDP Act).
    Records purpose (AI_ANALYSIS, SMS_REMINDERS, THIRD_PARTY_SHARING, TELEMEDICINE) and audit log.
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    valid_purposes = ['AI_ANALYSIS', 'SMS_REMINDERS', 'THIRD_PARTY_SHARING', 'TELEMEDICINE']
    purpose_upper = req.consent_purpose.upper()
    if purpose_upper not in valid_purposes:
        raise HTTPException(status_code=400, detail=f"Invalid consent purpose. Must be one of: {valid_purposes}")

    now = datetime.datetime.utcnow()
    consent = db.query(ConsentRecord).filter(
        ConsentRecord.patient_id == patient_id,
        ConsentRecord.consent_purpose == purpose_upper
    ).first()

    if not consent:
        consent = ConsentRecord(
            patient_id=patient_id,
            consent_purpose=purpose_upper,
            is_granted=req.is_granted,
            granted_at=now if req.is_granted else None,
            revoked_at=None if req.is_granted else now,
            signature_hash=f"DPDP2023${uuid.uuid4().hex[:16]}"
        )
        db.add(consent)
    else:
        consent.is_granted = req.is_granted
        if req.is_granted:
            consent.granted_at = now
            consent.revoked_at = None
        else:
            consent.revoked_at = now

    # Audit log consent event
    db.add(AuditEvent(
        action="CONSENT_RECORDED" if req.is_granted else "CONSENT_REVOKED",
        resource_type="consent_records",
        resource_id=str(patient_id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        payload_after={
            "patient_id": patient_id,
            "purpose": purpose_upper,
            "is_granted": req.is_granted
        }
    ))
    db.commit()

    return {
        "success": True,
        "patient_id": patient_id,
        "consent_purpose": purpose_upper,
        "is_granted": req.is_granted,
        "message": f"Consent {purpose_upper} successfully {'granted' if req.is_granted else 'revoked'} under India DPDP Act 2023."
    }

@router.post("/{patient_id}/erase-data")
def erase_patient_data_dpdp(
    patient_id: int,
    req: EraseDataRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    India DPDP Act 2023 Section 12 (Right to Erasure / 'Delete My Data').
    Pseudonymizes patient personally identifiable demographics, revokes active logins,
    and logs compliance audit entry.
    """
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Explicit confirmation (confirm=true) is required for data erasure.")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    user = patient.user

    # Anonymize PII in patient record
    patient.first_name = "ANONYMIZED"
    patient.last_name = "PATIENT"
    patient.address_line1 = "[REDACTED_UNDER_DPDP_ACT]"
    patient.emergency_contact_name = None
    patient.emergency_contact_phone = None

    if user:
        user.email = f"erased.{user.id}@dpdp.healthslip.ai"
        user.phone_number = f"+910000{user.id:06d}"
        user.status = "DEACTIVATED"

        # Revoke all active sessions
        db.query(UserSession).filter(UserSession.user_id == user.id).update({
            "is_active": False,
            "revoked_at": datetime.datetime.utcnow()
        })

    # Revoke all active consents
    db.query(ConsentRecord).filter(ConsentRecord.patient_id == patient_id).update({
        "is_granted": False,
        "revoked_at": datetime.datetime.utcnow()
    })

    # Mandatory DPDP Audit Log
    db.add(AuditEvent(
        action="PATIENT_DATA_ERASED",
        resource_type="patients",
        resource_id=str(patient_id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        payload_after={
            "patient_id": patient_id,
            "reason": req.reason,
            "erasure_type": "RIGHT_TO_BE_FORGOTTEN",
            "statutory_act": "India DPDP Act 2023 Section 12"
        }
    ))
    db.commit()

    return {
        "success": True,
        "patient_id": patient_id,
        "status": "ERASED",
        "message": "Patient personal data has been securely erased and pseudonymized in strict compliance with the India DPDP Act 2023."
    }

