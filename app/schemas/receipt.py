from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

class ReceiptItemBase(BaseModel):
    item_type: str = Field("CONSULTATION", description="CONSULTATION, MEDICATION, LAB_TEST, PROCEDURE")
    item_name: str
    unit_price: float = Field(ge=0.0)
    quantity: int = Field(default=1, ge=1)
    total_price: Optional[float] = None
    dosage: Optional[str] = None
    instructions: Optional[str] = None

class ReceiptItemCreate(ReceiptItemBase):
    pass

class ReceiptItemResponse(ReceiptItemBase):
    id: int
    health_slip_id: int

    model_config = ConfigDict(from_attributes=True)

class MedicationReminderBase(BaseModel):
    medicine_name: str
    dosage: str
    timing_slot: str = Field("MORNING", description="MORNING, AFTERNOON, EVENING, NIGHT")
    schedule_time: str = Field("08:00 AM")
    instructions: Optional[str] = "Take with water"
    duration_days: int = Field(default=5, ge=1)

class MedicationReminderCreate(MedicationReminderBase):
    pass

class MedicationReminderResponse(MedicationReminderBase):
    id: int
    health_slip_id: int
    patient_id: int
    is_done: bool
    last_taken_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PatientEmbeddedCreate(BaseModel):
    full_name: str
    age: int
    gender: str
    phone: str
    email: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None

class HealthSlipCreate(BaseModel):
    # Patient info
    patient: PatientEmbeddedCreate
    
    # Doctor info
    doctor_name: str = "Dr. K. S. Rao, M.B.B.S., M.D."
    doctor_license: str = "TSMC-2024-8841"
    clinic_name: str = "HealthSlip AI Multi-Specialty Clinic & Seva Kendra"
    
    # Clinical info
    symptoms: Optional[str] = None
    diagnosis: str
    clinical_notes: Optional[str] = None
    ai_insights: Optional[str] = None
    
    # Line items & Reminders
    items: List[ReceiptItemCreate] = []
    reminders: List[MedicationReminderCreate] = []
    
    # Financials
    tax_percent: float = Field(default=5.0, ge=0.0)
    discount_amount: float = Field(default=0.0, ge=0.0)
    insurance_covered: float = Field(default=0.0, ge=0.0)
    payment_status: str = "PAID"
    payment_method: str = "UPI/Card"

class HealthSlipResponse(BaseModel):
    id: int
    slip_number: str
    visit_date: datetime
    symptoms: Optional[str] = None
    diagnosis: Optional[str] = None
    clinical_notes: Optional[str] = None
    ai_insights: Optional[str] = None
    
    subtotal: float
    tax_percent: float
    tax_amount: float
    discount_amount: float
    insurance_covered: float
    grand_total: float
    payment_status: str
    payment_method: str
    verification_hash: str
    status: str
    
    doctor_name: str
    clinic_name: str
    patient_name: str
    patient_phone: str
    patient_age: int
    patient_gender: str
    
    items: List[ReceiptItemResponse] = []
    reminders: List[MedicationReminderResponse] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class HealthSlipSummary(BaseModel):
    id: int
    slip_number: str
    visit_date: datetime
    patient_name: str
    patient_phone: str
    doctor_name: str
    diagnosis: Optional[str] = None
    grand_total: float
    payment_status: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PublicVerificationResponse(BaseModel):
    is_valid: bool
    slip_number: str
    verification_hash: str
    issued_date: datetime
    clinic_name: str
    doctor_name: str
    patient_masked_name: str # Masked for HIPAA/privacy e.g., "M*** N*****"
    payment_status: str
    grand_total: float
    status: str
    tamper_proof_status: str
    message: str
