import datetime
from pydantic import BaseModel, Field
from typing import Optional, List

class UserProfileSchema(BaseModel):
    id: int
    uuid: str
    email: str
    phone_number: str
    full_name: str
    roles: List[str] = []
    primary_role: str = "PATIENT"
    status: str = "ACTIVE"
    practitioner_license: Optional[str] = None
    practitioner_specialization: Optional[str] = None
    last_login_at: Optional[datetime.datetime] = None
    created_at: Optional[datetime.datetime] = None

class LoginRequest(BaseModel):
    email_or_phone: str = Field(..., description="Email address or registered mobile number")
    password: str = Field(..., min_length=4, description="User password")
    remember_me: bool = Field(False, description="Persist session for longer period")

class OtpLoginRequest(BaseModel):
    phone_number: str = Field(..., description="Registered mobile number")
    otp_code: str = Field(..., min_length=4, max_length=6, description="6-digit verification code")

class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=128, description="User's full legal name")
    email: str = Field(..., min_length=5, max_length=191, description="Unique email address")
    phone_number: str = Field(..., min_length=6, max_length=20, description="Unique mobile number")
    password: str = Field(..., min_length=6, max_length=128, description="Secure user password")
    role_code: str = Field("PATIENT", description="DOCTOR, PATIENT, or ADMIN")
    gender: Optional[str] = Field("Male", description="Male, Female, Other")
    date_of_birth: Optional[str] = Field(None, description="Date of birth YYYY-MM-DD")
    doctor_license: Optional[str] = Field(None, description="Medical license number if doctor")
    doctor_specialization: Optional[str] = Field("General Medicine", description="Specialization if doctor")

class AuthResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in_seconds: Optional[int] = None
    user: Optional[UserProfileSchema] = None

class SessionStatusResponse(BaseModel):
    authenticated: bool
    message: str
    user: Optional[UserProfileSchema] = None
    session_id: Optional[int] = None
    expires_at: Optional[str] = None

class ActiveSessionSchema(BaseModel):
    id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime.datetime
    is_active: bool
    is_current: bool = False
