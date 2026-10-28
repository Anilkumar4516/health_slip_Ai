from pydantic import BaseModel, Field
from typing import List, Optional
from app.schemas.receipt import ReceiptItemCreate, MedicationReminderCreate

class AIExtractRequest(BaseModel):
    clinical_notes: str = Field(..., description="Doctor's clinical notes, prescribed drugs, symptoms, diagnosis, lab tests")
    patient_name: Optional[str] = "Minh Nguyen"
    patient_age: Optional[int] = 29
    patient_gender: Optional[str] = "Male"
    patient_phone: Optional[str] = "+1 555-019-2834"

class AIExtractedResponse(BaseModel):
    patient_name: str
    patient_age: int
    patient_gender: str
    patient_phone: str
    symptoms: str
    diagnosis: str
    items: List[ReceiptItemCreate]
    reminders: List[MedicationReminderCreate]
    clinical_advice: str
    safety_warnings: List[str]
    suggested_follow_up_days: int
    confidence_score: float
    raw_ai_summary: str
