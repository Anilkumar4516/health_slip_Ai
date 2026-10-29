import os
import datetime
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base, SessionLocal, get_db_status
from app.routes import receipts, otp, reminders, verification, stats, auth, pharmacy, realtime, patients
from app.models.receipt import Receipt
from app.models.user import Role, User, UserRole
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder
from app.schemas.receipt import HealthSlipCreate, ReceiptItemCreate, MedicationReminderCreate, PatientEmbeddedCreate
from app.services.receipt_service import ReceiptService
from app.services.auth_service import AuthService
from app.services.generic_drug_service import GenericDrugService
from app.services.websocket_manager import ws_manager

# Safe create_all (skips existing tables)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[Database] Schema already verified ({e})")

def seed_initial_demo_data():
    """Seed sample doctor, patient Minh, and demo HealthSlip into MySQL healthslip_prod"""
    db = SessionLocal()
    try:
        # Seed default RBAC roles if empty
        if db.query(Role).count() == 0:
            roles = [
                Role(code="ADMIN", name="System Administrator", description="Full administrative access"),
                Role(code="DOCTOR", name="Medical Practitioner", description="Prescribes and manages clinical slips"),
                Role(code="PHARMACIST", name="Clinical Pharmacist", description="Dispenses medications and checks interactions"),
                Role(code="PATIENT", name="Patient User", description="Access personal health slips and reminders")
            ]
            db.add_all(roles)
            db.commit()

        receipt_count = db.query(Receipt).count()
        if receipt_count == 0:
            demo_payload = HealthSlipCreate(
                patient=PatientEmbeddedCreate(
                    full_name="Minh",
                    age=28,
                    gender="Male",
                    phone="+1 555-019-2834",
                    email="minh.patient@example.com",
                    blood_group="O+",
                    address="452 Elm Street, Medical Arts District"
                ),
                doctor_name="Dr. Minh Nguyen, M.D.",
                doctor_license="MED-2024-8841",
                clinic_name="HealthSlip AI Medical Center",
                diagnosis="Acute Tension Migraine & Mild Rhinovirus",
                symptoms="Severe tension headache, nasal congestion, seasonal fatigue",
                clinical_notes="Patient presented with acute tension headache. Advised adequate hydration, rest, and prescribed Ibuprofen regimen.",
                ai_insights="Prescribed NSAID therapy. Contraindications checked: No reported NSAID allergy. Reminder: take with meals.",
                items=[
                    ReceiptItemCreate(
                        item_type="CONSULTATION",
                        item_name="Physician Consultation & Health Exam",
                        unit_price=50.0,
                        quantity=1,
                        instructions="General diagnostic assessment"
                    ),
                    ReceiptItemCreate(
                        item_type="MEDICATION",
                        item_name="Ibuprofen 400mg Film-Coated",
                        unit_price=12.0,
                        quantity=1,
                        dosage="1 pill",
                        instructions="Take with water after meals"
                    ),
                    ReceiptItemCreate(
                        item_type="MEDICATION",
                        item_name="Ibuprofen metisylat",
                        unit_price=13.0,
                        quantity=1,
                        dosage="1 pill",
                        instructions="Take after lunch"
                    )
                ],
                reminders=[
                    MedicationReminderCreate(
                        medicine_name="Ibuprofen",
                        dosage="1 pill",
                        timing_slot="MORNING",
                        schedule_time="12:00 am",
                        instructions="Take with water",
                        duration_days=5
                    ),
                    MedicationReminderCreate(
                        medicine_name="Ibuprofen metisylat",
                        dosage="1 pill",
                        timing_slot="AFTERNOON",
                        schedule_time="After lunch",
                        instructions="Take with full glass of water",
                        duration_days=5
                    ),
                    MedicationReminderCreate(
                        medicine_name="Ibuprofen",
                        dosage="1 pill",
                        timing_slot="AFTERNOON",
                        schedule_time="Afternoon",
                        instructions="Post-lunch dosage",
                        duration_days=5
                    )
                ],
                tax_percent=4.0,
                discount_amount=0.0,
                insurance_covered=0.0,
                payment_status="PAID",
                payment_method="Apple Pay / NFC"
            )
            ReceiptService.create_health_slip(db, demo_payload)
            print("[Seed] Successfully seeded initial demo records into MySQL healthslip_prod!")
            
        # Ensure user roles and passwords are updated with PBKDF2
        doctor_role = db.query(Role).filter(Role.code == "DOCTOR").first()
        patient_role = db.query(Role).filter(Role.code == "PATIENT").first()
        admin_role = db.query(Role).filter(Role.code == "ADMIN").first()

        # Update Doctor password if needed
        dr = db.query(User).filter(User.email == "dr.minh@healthslip.ai").first()
        if dr and not dr.password_hash.startswith("pbkdf2_sha256$"):
            dr.password_hash = AuthService.hash_password("Doctor@2026")

        # Update Patient password if needed
        pt = db.query(User).filter(User.email == "minh.patient@example.com").first()
        if pt and not pt.password_hash.startswith("pbkdf2_sha256$"):
            pt.password_hash = AuthService.hash_password("Patient@2026")

        # Ensure Admin user exists
        admin = db.query(User).filter(User.email == "admin@healthslip.ai").first()
        if not admin and admin_role:
            admin = User(
                email="admin@healthslip.ai",
                phone_number="+15550009999",
                password_hash=AuthService.hash_password("Admin@2026"),
                status="ACTIVE",
                is_phone_verified=True,
                is_email_verified=True
            )
            db.add(admin)
            db.flush()
            db.add(UserRole(user_id=admin.id, role_id=admin_role.id))

        if doctor_role and patient_role:
            for u in db.query(User).all():
                existing = db.query(UserRole).filter(UserRole.user_id == u.id).first()
                if not existing:
                    if u.practitioner:
                        db.add(UserRole(user_id=u.id, role_id=doctor_role.id))
                    elif u.patient:
                        db.add(UserRole(user_id=u.id, role_id=patient_role.id))
            db.commit()
    except Exception as e:
        print(f"[Seed] Seeding note: {e}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bind event loop for real-time WebSocket broadcasting
    try:
        ws_manager.set_loop(asyncio.get_running_loop())
    except Exception:
        pass

    # Ensure tables are created
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass

    seed_initial_demo_data()

    # Seed Urban & Rural Pharmacy Inventory
    db = SessionLocal()
    try:
        GenericDrugService.seed_inventory_if_empty(db)
    finally:
        db.close()

    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Assisted Medical Receipt Generation and OTP-Based Patient Verification System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
os.makedirs("app/static/css", exist_ok=True)
os.makedirs("app/static/js", exist_ok=True)
os.makedirs("app/static/img", exist_ok=True)
os.makedirs("app/templates", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include API Routers
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(receipts.router)
app.include_router(pharmacy.router)
app.include_router(realtime.router)
app.include_router(otp.router)
app.include_router(reminders.router)
app.include_router(verification.router)
app.include_router(stats.router)

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "database": get_db_status(),
        "dev_sandbox_otp": settings.DEV_OTP_SANDBOX_MODE,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

@app.get("/", response_class=HTMLResponse)
def serve_index():
    return FileResponse("app/templates/index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8005))
    host = os.environ.get("HOST", "0.0.0.0")
    reload = os.environ.get("ENVIRONMENT", "development").lower() == "development"
    uvicorn.run("main:app", host=host, port=port, reload=reload)
