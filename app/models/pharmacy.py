import datetime
from sqlalchemy import Column, BigInteger, Integer, Float, String, DateTime, Date, Enum, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import BIGINT as MySQL_BIGINT
from app.database import Base

def BigIntPK():
    return Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)

def BigIntFK(foreign_key: str, nullable: bool = True, ondelete: str = "SET NULL", unique: bool = False):
    return Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), ForeignKey(foreign_key, ondelete=ondelete), nullable=nullable, unique=unique)

class PharmacyStore(Base):
    __tablename__ = "pharmacy_stores"

    id = BigIntPK()
    name = Column(String(150), nullable=False)
    store_type = Column(String(20), default="URBAN") # URBAN or RURAL
    drug_license_number = Column(String(100), nullable=False) # e.g. DL: 20-B/48912 & 21-B/48913
    gstin = Column(String(20), nullable=True) # e.g. 36AAAAA0000A1Z5
    address = Column(String(255), nullable=True)
    city = Column(String(64), default="Hyderabad")
    state = Column(String(64), default="Telangana")
    postal_code = Column(String(20), default="500001")
    phone = Column(String(30), nullable=True)
    email = Column(String(120), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    users = relationship("User", back_populates="store", foreign_keys="User.store_id")
    dispense_orders = relationship("DispenseOrder", back_populates="store")
    inventory_batches = relationship("StoreInventoryBatch", back_populates="store", cascade="all, delete-orphan")

class PharmacyMedicineStock(Base):
    __tablename__ = "pharmacy_medicine_stock"

    id = BigIntPK()
    store_id = BigIntFK("pharmacy_stores.id", nullable=True, ondelete="SET NULL")
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
    vernacular_dosage_te = Column(String(255), default="భోజనం తర్వాత నీటితో తీసుకోండి")
    vernacular_dosage_hi = Column(String(255), nullable=True, default="భోజనం తర్వాత నీటితో తీసుకోండి")
    vernacular_dosage_en = Column(String(255), default="Take after meals with water")
    visual_timing = Column(String(50), default="MORNING_NIGHT") # MORNING, AFTERNOON, NIGHT, MORNING_NIGHT
    drug_schedule = Column(String(20), default="OTC") # OTC, SCHEDULE_H, SCHEDULE_H1, SCHEDULE_X
    is_controlled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class DispenseOrder(Base):
    __tablename__ = "dispense_orders"

    id = BigIntPK()
    slip_number = Column(String(50), nullable=False, index=True)
    store_id = BigIntFK("pharmacy_stores.id", nullable=True, ondelete="SET NULL")
    patient_name = Column(String(120), nullable=False)
    patient_phone = Column(String(30), nullable=False)
    doctor_name = Column(String(120), default="Dr. K. S. Rao, M.B.B.S., M.D.")
    diagnosis = Column(String(255), default="General Consultation")
    store_type = Column(String(20), default="URBAN") # URBAN or RURAL
    status = Column(String(30), default="RECEIVED") # RECEIVED, PREPARING, READY_FOR_PICKUP, DISPENSED, CANCELLED
    is_generic_substituted = Column(Boolean, default=False)
    generic_savings_amount = Column(Float, default=0.0)
    total_bill_amount = Column(Float, default=0.0)
    batch_number_dispensed = Column(String(100), default="B-2026-001")
    pharmacist_notes = Column(Text, nullable=True)
    pharmacist_user_id = BigIntFK("users.id", nullable=True, ondelete="SET NULL")
    schedule_confirmed = Column(Boolean, default=False)
    cryptographic_lock = Column(String(64), nullable=True) # Locks prescription against double dispensing
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    dispensed_at = Column(DateTime, nullable=True)

    store = relationship("PharmacyStore", back_populates="dispense_orders")
    pharmacist_user = relationship("User", foreign_keys=[pharmacist_user_id])

class StoreInventoryBatch(Base):
    __tablename__ = "store_inventory_batches"

    id = BigIntPK()
    store_id = BigIntFK("pharmacy_stores.id", nullable=False, ondelete="CASCADE")
    brand_name = Column(String(150), nullable=False, index=True)
    generic_name = Column(String(150), nullable=False, index=True)
    batch_no = Column(String(64), nullable=False, index=True)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    mrp = Column(Float, nullable=False, default=0.0)
    purchase_price = Column(Float, nullable=False, default=0.0)
    hsn_code = Column(String(20), default="3004")
    gst_rate = Column(Float, default=12.0)
    drug_schedule = Column(String(20), default="OTC") # OTC, SCHEDULE_H, SCHEDULE_H1, SCHEDULE_X
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    store = relationship("PharmacyStore", back_populates="inventory_batches")

