from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class DispenseRequest(BaseModel):
    slip_number: str = Field(..., description="The unique medical slip number e.g. HSL-2026-94670")
    store_type: str = Field("URBAN", description="URBAN (high-volume POS) or RURAL (Seva Store / Jan Aushadhi)")
    pharmacist_name: str = Field("Senior Clinical Pharmacist", description="Name of dispensing clinician")
    is_generic_substituted: bool = Field(False, description="Whether Jan Aushadhi low-cost generic salts were substituted")
    notes: Optional[str] = Field(None, description="Pharmacist verification or dispensing notes")

class GenericSubstituteRequest(BaseModel):
    medicine_name: str = Field(..., description="Brand name of prescribed medicine e.g. Augmentin 625mg")

class StockAdjustRequest(BaseModel):
    medicine_id: int
    quantity_change: int = Field(..., description="Positive to add stock, negative to deduct")

class AudioDosageRequest(BaseModel):
    medicine_name: str
    schedule_time: Optional[str] = "After lunch"
    language: str = Field("hi", description="'hi' for Hindi, 'en' for English")

class RuralSmsRequest(BaseModel):
    slip_number: str
    patient_phone: Optional[str] = None
