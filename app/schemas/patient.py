from typing import Optional, List
from pydantic import BaseModel, Field
import datetime

class PatientManualCreate(BaseModel):
    first_name: str = Field(..., min_length=1, description="Patient first name")
    last_name: Optional[str] = Field("", description="Patient last or family name")
    phone: str = Field(..., min_length=5, description="Mobile number for SMS/OTP prescription access")
    email: Optional[str] = Field(None, description="Patient email address")
    age: Optional[int] = Field(28, ge=0, le=130, description="Patient age in years")
    date_of_birth: Optional[str] = Field(None, description="Date of birth YYYY-MM-DD")
    gender: str = Field("Male", description="Male, Female, Other, Undisclosed")
    blood_group: Optional[str] = Field("O+", description="A+, A-, B+, B-, AB+, AB-, O+, O-, UNKNOWN")
    address_line1: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field("Hyderabad", description="City")
    state: Optional[str] = Field("Telangana", description="State")
    postal_code: Optional[str] = Field("500001", description="Postal / Pin code")
    emergency_contact_name: Optional[str] = Field(None, description="Emergency contact person")
    emergency_contact_phone: Optional[str] = Field(None, description="Emergency contact phone")
    allergies: Optional[str] = Field(None, description="Known drug or food allergies")
    medical_history: Optional[str] = Field(None, description="Pre-existing conditions or medical history")

class PatientSummary(BaseModel):
    id: int
    uuid: str
    full_name: str
    first_name: str
    last_name: str = ""
    phone: str
    email: Optional[str] = None
    age: int = 28
    gender: str = "Male"
    blood_group: str = "O+"
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

class PatientDetailResponse(PatientSummary):
    address_line1: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    total_prescriptions: int = 0
    total_bills: int = 0

class ConsentCaptureRequest(BaseModel):
    consent_purpose: str = Field("AI_ANALYSIS", description="AI_ANALYSIS, SMS_REMINDERS, THIRD_PARTY_SHARING, or TELEMEDICINE")
    is_granted: bool = Field(True, description="Whether consent is given or revoked")

class EraseDataRequest(BaseModel):
    reason: Optional[str] = Field("Data Principal erasure request under India DPDP Act 2023", description="Reason for deletion request")
    confirm: bool = Field(True, description="Explicit confirmation of erasure")

