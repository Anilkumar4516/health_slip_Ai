from pydantic import BaseModel, Field
from typing import Optional

class OtpRequestSchema(BaseModel):
    phone_number: str = Field(..., description="Patient mobile number with or without country code")
    receipt_number: Optional[str] = Field(None, description="Optional specific HealthSlip receipt number")

class OtpVerifySchema(BaseModel):
    phone_number: str = Field(..., description="Patient mobile number")
    otp_code: str = Field(..., min_length=4, max_length=6, description="4 or 6-digit OTP code")
    receipt_number: Optional[str] = None

class OtpResponseSchema(BaseModel):
    success: bool
    message: str
    phone_number: str
    receipt_number: Optional[str] = None
    expires_in_seconds: Optional[int] = None
    sandbox_otp: Optional[str] = None # Available in development/sandbox mode for immediate evaluation
    access_token: Optional[str] = None
