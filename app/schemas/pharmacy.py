from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class DispenseLineItem(BaseModel):
    item_name: str
    quantity_to_dispense: int = Field(1, ge=1)
    batch_no: Optional[str] = None

class DispenseRequest(BaseModel):
    slip_number: str = Field(..., description="The unique medical slip number e.g. HSL-2026-94670")
    store_id: Optional[int] = Field(None, description="ID of the dispensing PharmacyStore")
    store_type: str = Field("URBAN", description="URBAN (high-volume POS) or RURAL (Seva Store / Jan Aushadhi)")
    pharmacist_name: str = Field("Senior Clinical Pharmacist", description="Name of dispensing clinician")
    is_generic_substituted: bool = Field(False, description="Whether Jan Aushadhi low-cost generic salts were substituted")
    generic_substitution_confirmed: bool = Field(False, description="Pharmacist explicit confirmation for generic substitution")
    schedule_confirmed: bool = Field(False, description="Pharmacist confirmation for dispensing Schedule H/H1/X drugs")
    client_sync_id: Optional[str] = Field(None, description="Idempotent client transaction UUID for offline-first sync")
    line_items: Optional[List[DispenseLineItem]] = Field(None, description="Per-line items to dispense for partial dispensing")
    notes: Optional[str] = Field(None, description="Pharmacist verification or dispensing notes")

class GenericSubstituteRequest(BaseModel):
    medicine_name: str = Field(..., description="Brand name of prescribed medicine e.g. Augmentin 625mg")

class StockAdjustRequest(BaseModel):
    medicine_id: int
    quantity_change: int = Field(..., description="Positive to add stock, negative to deduct")

class AudioDosageRequest(BaseModel):
    medicine_name: str
    schedule_time: Optional[str] = "After lunch"
    language: str = Field("te", description="'te' for Telugu (తెలుగు), 'en' for English")

class RuralSmsRequest(BaseModel):
    slip_number: str
    patient_phone: Optional[str] = None

class AddMedicineStockRequest(BaseModel):
    brand_name: str = Field(..., description="Brand or trade name e.g. Augmentin 625mg")
    generic_name: str = Field(..., description="Chemical or generic salt name")
    dosage_form: str = Field("Tablet", description="Tablet, Capsule, Syrup, etc.")
    strength: str = Field("500mg", description="Dosage strength e.g. 500mg, 625mg")
    batch_number: str = Field(..., description="Manufacturing batch number e.g. B-2026-901")
    stock_quantity: int = Field(50, description="Initial stock quantity")
    reorder_level: int = Field(15, description="Low stock warning threshold")
    unit_price_brand: float = Field(10.0, description="Branded market price")
    unit_price_generic: float = Field(2.0, description="Jan Aushadhi government generic price")
    vernacular_dosage_te: Optional[str] = "భోజనం తర్వాత నీటితో తీసుకోండి"
    vernacular_dosage_hi: Optional[str] = "భోజనం తర్వాత నీటితో తీసుకోండి"
    vernacular_dosage_en: Optional[str] = "Take after meals with water"
    visual_timing: str = "AFTER_MEAL"
    is_controlled: bool = False


