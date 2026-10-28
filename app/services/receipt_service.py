import hmac
import hashlib
import io
import base64
import random
import datetime
import uuid
import qrcode
from typing import Dict, Any, Tuple, Optional, List
from sqlalchemy.orm import Session
from app.config import settings
from app.models.user import User, Patient, Practitioner, Role
from app.models.receipt import Medicine, Prescription, PrescriptionItem, DoseSchedule, Bill, BillItem, Receipt, Reminder
from app.models.verification import AuditEvent
from app.schemas.receipt import HealthSlipCreate, HealthSlipResponse, ReceiptItemResponse, MedicationReminderResponse

class ReceiptService:
    @staticmethod
    def generate_slip_number() -> str:
        """Generate unique medical slip identifier e.g. HSL-2026-87421"""
        year = datetime.datetime.utcnow().year
        rand_id = random.randint(10000, 99999)
        return f"HSL-{year}-{rand_id}"

    @staticmethod
    def calculate_verification_hash(slip_number: str, patient_phone: str, grand_total: float, visit_date_iso: str) -> str:
        """Compute cryptographic HMAC-SHA256 signature to guarantee slip immutability"""
        payload = f"{slip_number}|{patient_phone}|{grand_total:.2f}|{visit_date_iso}".encode("utf-8")
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def generate_qr_code_base64(verification_url: str) -> str:
        """Generate QR code PNG as base64 string"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(verification_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#1E3A8A", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode("utf-8")

    @staticmethod
    def mask_name(name: str) -> str:
        """Mask name for public verification scan e.g. 'Minh Nguyen' -> 'M*** N*****'"""
        if not name:
            return "P******"
        parts = name.split()
        masked_parts = []
        for part in parts:
            if len(part) <= 2:
                masked_parts.append(part[0] + "*")
            else:
                masked_parts.append(part[0] + "*" * (len(part) - 1))
        return " ".join(masked_parts)

    @staticmethod
    def parse_time_str(time_str: str) -> datetime.time:
        """Parse human time string like '12:00 am', 'After lunch', '08:00 pm' to datetime.time"""
        t_lower = (time_str or "").lower()
        if "after lunch" in t_lower or "13:" in t_lower:
            return datetime.time(13, 0)
        elif "afternoon" in t_lower or "16:" in t_lower:
            return datetime.time(16, 0)
        elif "evening" in t_lower or "20:" in t_lower or "8 pm" in t_lower:
            return datetime.time(20, 0)
        elif "night" in t_lower or "22:" in t_lower or "10 pm" in t_lower:
            return datetime.time(22, 0)
        elif "12:00 am" in t_lower or "midnight" in t_lower:
            return datetime.time(0, 0)
        elif "am" in t_lower:
            try:
                dt = datetime.datetime.strptime(time_str.strip(), "%I:%M %p")
                return dt.time()
            except:
                return datetime.time(8, 0)
        elif "pm" in t_lower:
            try:
                dt = datetime.datetime.strptime(time_str.strip(), "%I:%M %p")
                return dt.time()
            except:
                return datetime.time(20, 0)
        return datetime.time(8, 0)

    @staticmethod
    def create_health_slip(db: Session, slip_data: HealthSlipCreate) -> Any:
        """
        Creates production records across enterprise tables in healthslip_prod:
        practitioners, users, patients, prescriptions, medicines, prescription_items,
        dose_schedules, reminders, bills, bill_items, receipts, audit_events.
        """
        # 1. Find or create Practitioner (Doctor)
        practitioner = db.query(Practitioner).filter(Practitioner.license_number == slip_data.doctor_license).first()
        if not practitioner:
            doc_user = db.query(User).filter(User.email == "dr.minh@healthslip.ai").first()
            if not doc_user:
                doc_user = User(
                    uuid=str(uuid.uuid4()),
                    email="dr.minh@healthslip.ai",
                    phone_number="+15552345678",
                    password_hash="sha256$practitioner$hash",
                    status="ACTIVE",
                    is_phone_verified=True,
                    is_email_verified=True
                )
                db.add(doc_user)
                db.flush()

            practitioner = Practitioner(
                user_id=doc_user.id,
                license_number=slip_data.doctor_license,
                specialization="General & Internal Medicine",
                department="Clinical Diagnostics"
            )
            db.add(practitioner)
            db.flush()

        # 2. Find or create Patient & User account
        clean_phone = slip_data.patient.phone.strip().replace(" ", "").replace("-", "")
        patient_user = db.query(User).filter(User.phone_number == clean_phone).first()
        
        name_parts = slip_data.patient.full_name.strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else "Patient"

        if not patient_user:
            email_slug = f"{first_name.lower()}.{random.randint(100, 999)}@patient.healthslip.ai"
            patient_user = User(
                uuid=str(uuid.uuid4()),
                email=slip_data.patient.email or email_slug,
                phone_number=clean_phone,
                password_hash="sha256$patient$otp_verified",
                status="ACTIVE",
                is_phone_verified=True
            )
            db.add(patient_user)
            db.flush()

        patient = db.query(Patient).filter(Patient.user_id == patient_user.id).first()
        if not patient:
            patient = Patient(
                uuid=str(uuid.uuid4()),
                user_id=patient_user.id,
                first_name=first_name,
                last_name=last_name,
                date_of_birth=datetime.date(datetime.date.today().year - slip_data.patient.age, 1, 1),
                gender='MALE' if slip_data.patient.gender.upper().startswith('M') else 'FEMALE',
                blood_group=slip_data.patient.blood_group or 'O+',
                emergency_contact_phone=clean_phone,
                address_line1=slip_data.patient.address or "452 Elm Street"
            )
            db.add(patient)
            db.flush()

        # 3. Create Prescription
        now = datetime.datetime.utcnow()
        prescription = Prescription(
            uuid=str(uuid.uuid4()),
            patient_id=patient.id,
            practitioner_id=practitioner.id,
            diagnosis=slip_data.diagnosis,
            ocr_raw_text=slip_data.clinical_notes,
            status="ACTIVE",
            issued_date=now.date(),
            valid_until=(now + datetime.timedelta(days=30)).date()
        )
        db.add(prescription)
        db.flush()

        # 4. Create Medicines, PrescriptionItems, DoseSchedules, Reminders
        created_reminders = []
        for rem in slip_data.reminders:
            # Find or create medicine
            med = db.query(Medicine).filter(Medicine.brand_name == rem.medicine_name).first()
            if not med:
                med = Medicine(
                    brand_name=rem.medicine_name,
                    generic_name=rem.medicine_name,
                    dosage_form='TABLET',
                    strength=rem.dosage
                )
                db.add(med)
                db.flush()

            # Prescription Item
            p_item = PrescriptionItem(
                prescription_id=prescription.id,
                medicine_id=med.id,
                dosage_quantity=rem.dosage,
                frequency=rem.timing_slot,
                route='ORAL',
                duration_days=rem.duration_days,
                instructions=rem.instructions or "Take with water",
                total_quantity_prescribed=rem.duration_days * 2
            )
            db.add(p_item)
            db.flush()

            # Dose Schedule
            time_val = ReceiptService.parse_time_str(rem.schedule_time)
            dose_sched = DoseSchedule(
                prescription_item_id=p_item.id,
                scheduled_time=time_val,
                meal_relation='AFTER_MEAL',
                dose_amount=rem.dosage,
                is_active=True
            )
            db.add(dose_sched)
            db.flush()

            # Reminder
            reminder_record = Reminder(
                patient_id=patient.id,
                dose_schedule_id=dose_sched.id,
                reminder_type='DOSE_ALERT',
                scheduled_timestamp=datetime.datetime.combine(now.date(), time_val),
                status='PENDING'
            )
            db.add(reminder_record)
            created_reminders.append(reminder_record)

        # 5. Calculate Financials
        subtotal = 0.0
        calculated_items = []
        for item in slip_data.items:
            item_total = item.unit_price * item.quantity
            subtotal += item_total
            calculated_items.append((item, item_total))

        tax_amount = round(subtotal * (slip_data.tax_percent / 100.0), 2)
        grand_total = max(0.0, round(subtotal + tax_amount - slip_data.discount_amount - slip_data.insurance_covered, 2))

        # 6. Create Bill
        year = now.year
        inv_number = f"INV-{year}-{random.randint(10000, 99999)}"
        bill = Bill(
            invoice_number=inv_number,
            patient_id=patient.id,
            prescription_id=prescription.id,
            currency="INR",
            subtotal_cents=int(subtotal * 100),
            tax_cents=int(tax_amount * 100),
            discount_cents=int(slip_data.discount_amount * 100),
            total_cents=int(grand_total * 100),
            status="PAID" if slip_data.payment_status.upper() == "PAID" else "ISSUED",
            due_date=now.date()
        )
        db.add(bill)
        db.flush()

        # Add Bill Items
        for item_data, total_price in calculated_items:
            b_item = BillItem(
                bill_id=bill.id,
                description=f"{item_data.item_name} [{item_data.item_type}]",
                quantity=item_data.quantity,
                unit_price_cents=int(item_data.unit_price * 100),
                total_price_cents=int(total_price * 100)
            )
            db.add(b_item)

        # 7. Create Receipt with HMAC-SHA256 Cryptographic Seal
        slip_number = ReceiptService.generate_slip_number()
        v_hash = ReceiptService.calculate_verification_hash(
            slip_number=slip_number,
            patient_phone=clean_phone,
            grand_total=grand_total,
            visit_date_iso=now.strftime("%Y-%m-%d")
        )

        receipt = Receipt(
            receipt_number=slip_number,
            bill_id=bill.id,
            amount_paid_cents=int(grand_total * 100),
            payment_method='UPI' if 'UPI' in slip_data.payment_method.upper() else 'CARD',
            gateway_transaction_id=v_hash,
            gateway_response_payload={
                "verification_hash": v_hash,
                "symptoms": slip_data.symptoms,
                "clinical_notes": slip_data.clinical_notes,
                "ai_insights": slip_data.ai_insights
            },
            payment_status='SUCCESS',
            settled_at=now
        )
        db.add(receipt)

        # 8. Add Audit Event
        db.add(AuditEvent(
            actor_user_id=practitioner.user_id,
            action="CREATE_RECEIPT",
            resource_type="receipts",
            resource_id=slip_number,
            payload_after={"grand_total": grand_total, "invoice": inv_number}
        ))

        db.commit()
        db.refresh(receipt)
        db.refresh(bill)

        slip_result = ReceiptService.build_slip_view_model(bill, receipt)

        # Real-time WebSocket broadcast to all urban/rural medical stores & dashboards
        try:
            from app.services.websocket_manager import ws_manager
            ws_manager.sync_broadcast("NEW_PRESCRIPTION", {
                "slip_number": slip_number,
                "patient_name": patient.full_name if patient else "Patient",
                "patient_phone": clean_phone,
                "doctor_name": practitioner.name if practitioner else "Doctor",
                "diagnosis": slip_data.diagnosis,
                "grand_total": grand_total,
                "items_count": len(slip_data.items),
                "created_at": now.isoformat()
            })
        except Exception:
            pass

        return slip_result

    @staticmethod
    def build_slip_view_model(bill: Bill, receipt: Receipt) -> Dict[str, Any]:
        """Convert production Bill + Receipt records into API response format"""
        payload = receipt.gateway_response_payload or {}
        patient = bill.patient
        practitioner = bill.prescription.practitioner if bill.prescription else None

        items_data = []
        for it in bill.items:
            items_data.append({
                "id": it.id,
                "health_slip_id": bill.id,
                "item_type": "MEDICATION" if "MEDICATION" in it.description else "CONSULTATION",
                "item_name": it.description,
                "unit_price": it.unit_price_cents / 100.0,
                "quantity": it.quantity,
                "total_price": it.total_price_cents / 100.0,
                "dosage": "1 pill",
                "instructions": "Take as directed"
            })

        reminders_data = []
        if patient:
            for rem in patient.reminders:
                reminders_data.append({
                    "id": rem.id,
                    "health_slip_id": bill.id,
                    "patient_id": patient.id,
                    "medicine_name": rem.medicine_name,
                    "dosage": rem.dosage,
                    "timing_slot": rem.timing_slot,
                    "schedule_time": rem.schedule_time,
                    "instructions": rem.instructions,
                    "duration_days": 5,
                    "is_done": rem.is_done,
                    "created_at": rem.created_at
                })

        return {
            "id": bill.id,
            "slip_number": receipt.receipt_number,
            "visit_date": bill.created_at,
            "symptoms": payload.get("symptoms", "General checkup"),
            "diagnosis": bill.prescription.diagnosis if bill.prescription else "General Consultation",
            "clinical_notes": payload.get("clinical_notes", ""),
            "ai_insights": payload.get("ai_insights", "Verified via HealthSlip AI"),
            "subtotal": bill.subtotal_cents / 100.0,
            "tax_percent": 5.0,
            "tax_amount": bill.tax_cents / 100.0,
            "discount_amount": bill.discount_cents / 100.0,
            "insurance_covered": 0.0,
            "grand_total": bill.total_cents / 100.0,
            "payment_status": "PAID" if receipt.payment_status == "SUCCESS" else receipt.payment_status,
            "payment_method": receipt.payment_method,
            "verification_hash": receipt.gateway_transaction_id or "",
            "status": bill.status,
            "doctor_name": practitioner.name if practitioner else "Dr. Minh Nguyen, M.D.",
            "clinic_name": practitioner.clinic_name if practitioner else "HealthSlip AI Medical Center",
            "patient_name": patient.full_name if patient else "Minh",
            "patient_phone": patient.phone if patient else "+1 555-019-2834",
            "patient_age": patient.age if patient else 28,
            "patient_gender": patient.gender if patient else "Male",
            "items": items_data,
            "reminders": reminders_data,
            "created_at": receipt.created_at
        }

    @staticmethod
    def verify_slip_authenticity(db: Session, slip_number: str) -> Dict[str, Any]:
        """Public verification routine without exposing PHI"""
        receipt = db.query(Receipt).filter(Receipt.receipt_number == slip_number).first()
        if not receipt:
            return {
                "is_valid": False,
                "slip_number": slip_number,
                "verification_hash": "",
                "issued_date": datetime.datetime.utcnow(),
                "clinic_name": "",
                "doctor_name": "",
                "patient_masked_name": "",
                "payment_status": "UNKNOWN",
                "grand_total": 0.0,
                "status": "NOT_FOUND",
                "tamper_proof_status": "FAILED",
                "message": "No official medical receipt found matching this receipt number."
            }

        bill = receipt.bill
        patient_phone = bill.patient.phone if bill and bill.patient else ""
        grand_total = bill.total_cents / 100.0

        expected_hash = ReceiptService.calculate_verification_hash(
            slip_number=receipt.receipt_number,
            patient_phone=patient_phone.replace(" ", "").replace("-", ""),
            grand_total=grand_total,
            visit_date_iso=receipt.created_at.strftime("%Y-%m-%d")
        )

        is_tamper_free = hmac.compare_digest(expected_hash, receipt.gateway_transaction_id or "")

        practitioner = bill.prescription.practitioner if bill and bill.prescription else None

        return {
            "is_valid": is_tamper_free,
            "slip_number": receipt.receipt_number,
            "verification_hash": receipt.gateway_transaction_id or "",
            "issued_date": receipt.created_at,
            "clinic_name": practitioner.clinic_name if practitioner else "HealthSlip AI Medical Center",
            "doctor_name": practitioner.name if practitioner else "Dr. Minh Nguyen, M.D.",
            "patient_masked_name": ReceiptService.mask_name(bill.patient.full_name if bill and bill.patient else "Minh"),
            "payment_status": "PAID" if receipt.payment_status == "SUCCESS" else receipt.payment_status,
            "grand_total": grand_total,
            "status": bill.status if bill else "ACTIVE",
            "tamper_proof_status": "AUTHENTIC & VERIFIED" if is_tamper_free else "INTEGRITY_MISMATCH",
            "message": "Official medical receipt verified successfully via HealthSlip AI cryptographic seal." if is_tamper_free else "Receipt integrity check failed: potential tampering detected."
        }
