import datetime
from sqlalchemy import Column, BigInteger, Integer, Float, String, DateTime, Enum, Boolean, Text
from app.database import Base

class PharmacyMedicineStock(Base):
    __tablename__ = "pharmacy_medicine_stock"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    brand_name = Column(String(150), nullable=False, index=True)
    generic_name = Column(String(150), nullable=False, index=True)
    dosage_form = Column(String(50), default="Tablet")
    strength = Column(String(50), default="500mg")
    batch_number = Column(String(50), default="BATCH-2026-A1")
    stock_quantity = Column(Integer, default=100)
    reorder_level = Column(Integer, default=20)
    unit_price_brand = Column(Float, nullable=False, default=15.0)
    unit_price_generic = Column(Float, nullable=False, default=3.0)
    savings_percent = Column(Float, default=80.0)
    vernacular_dosage_hi = Column(String(255), default="भोजन के बाद पानी के साथ लें")
    vernacular_dosage_en = Column(String(255), default="Take after meals with water")
    visual_timing = Column(String(50), default="MORNING_NIGHT") # MORNING, AFTERNOON, NIGHT, MORNING_NIGHT
    is_controlled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class DispenseOrder(Base):
    __tablename__ = "dispense_orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slip_number = Column(String(50), nullable=False, index=True)
    patient_name = Column(String(120), nullable=False)
    patient_phone = Column(String(30), nullable=False)
    doctor_name = Column(String(120), default="Dr. Minh Nguyen, M.D.")
    diagnosis = Column(String(255), default="General Consultation")
    store_type = Column(String(20), default="URBAN") # URBAN or RURAL
    status = Column(String(30), default="RECEIVED") # RECEIVED, PREPARING, READY_FOR_PICKUP, DISPENSED, CANCELLED
    is_generic_substituted = Column(Boolean, default=False)
    generic_savings_amount = Column(Float, default=0.0)
    total_bill_amount = Column(Float, default=0.0)
    batch_number_dispensed = Column(String(100), default="B-2026-001")
    pharmacist_notes = Column(Text, nullable=True)
    cryptographic_lock = Column(String(64), nullable=True) # Locks prescription against double dispensing
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    dispensed_at = Column(DateTime, nullable=True)

