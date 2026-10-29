import datetime
import uuid
from sqlalchemy import Column, BigInteger, SmallInteger, Integer, String, DateTime, Date, Time, Enum, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    brand_name = Column(String(150), nullable=False)
    generic_name = Column(String(150), nullable=False)
    dosage_form = Column(Enum('TABLET', 'CAPSULE', 'SYRUP', 'INJECTION', 'OINTMENT', 'DROPS', 'INHALER', 'OTHER', name='med_form_enum'), default='TABLET')
    strength = Column(String(50), nullable=False, default="500mg")
    manufacturer = Column(String(150), nullable=True)
    is_controlled_substance = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    prescription_items = relationship("PrescriptionItem", back_populates="medicine")

class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    patient_id = Column(BigInteger, ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    practitioner_id = Column(BigInteger, ForeignKey("practitioners.id", ondelete="RESTRICT"), nullable=False)
    diagnosis = Column(Text, nullable=True)
    ocr_raw_text = Column(Text, nullable=True)
    prescription_image_url = Column(String(512), nullable=True)
    status = Column(Enum('DRAFT', 'ACTIVE', 'DISPENSED', 'CANCELLED', 'EXPIRED', name='presc_status_enum'), default='ACTIVE')
    issued_date = Column(Date, default=datetime.date.today, nullable=False)
    valid_until = Column(Date, default=lambda: datetime.date.today() + datetime.timedelta(days=30), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="prescriptions")
    practitioner = relationship("Practitioner", back_populates="prescriptions")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")
    bills = relationship("Bill", back_populates="prescription")

class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    prescription_id = Column(BigInteger, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False)
    medicine_id = Column(BigInteger, ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False)
    dosage_quantity = Column(String(50), nullable=False, default="1 tablet")
    frequency = Column(String(50), nullable=False, default="BID")
    route = Column(Enum('ORAL', 'IV', 'IM', 'TOPICAL', 'SUBLINGUAL', 'OPHTHALMIC', 'NASAL', name='route_enum'), default='ORAL')
    duration_days = Column(SmallInteger, nullable=False, default=5)
    instructions = Column(String(255), nullable=True, default="Take after meal with water")
    total_quantity_prescribed = Column(Integer, nullable=False, default=10)
    dispensed_quantity = Column(Integer, default=0)

    prescription = relationship("Prescription", back_populates="items")
    medicine = relationship("Medicine", back_populates="prescription_items")
    dose_schedules = relationship("DoseSchedule", back_populates="prescription_item", cascade="all, delete-orphan")

class DoseSchedule(Base):
    __tablename__ = "dose_schedules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    prescription_item_id = Column(BigInteger, ForeignKey("prescription_items.id", ondelete="CASCADE"), nullable=False)
    scheduled_time = Column(Time, nullable=False)
    meal_relation = Column(Enum('BEFORE_MEAL', 'WITH_MEAL', 'AFTER_MEAL', 'NO_RELATION', name='meal_relation_enum'), default='NO_RELATION')
    dose_amount = Column(String(30), default="1")
    is_active = Column(Boolean, default=True)

    prescription_item = relationship("PrescriptionItem", back_populates="dose_schedules")
    reminders = relationship("Reminder", back_populates="dose_schedule")

class Bill(Base):
    __tablename__ = "bills"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(BigInteger, ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    prescription_id = Column(BigInteger, ForeignKey("prescriptions.id", ondelete="SET NULL"), nullable=True)
    currency = Column(String(3), default="INR")
    subtotal_cents = Column(Integer, nullable=False, default=0)
    tax_cents = Column(Integer, default=0)
    discount_cents = Column(Integer, default=0)
    total_cents = Column(Integer, nullable=False, default=0)
    status = Column(Enum('ISSUED', 'PARTIALLY_PAID', 'PAID', 'VOID', 'REFUNDED', name='bill_status_enum'), default='PAID')
    due_date = Column(Date, default=datetime.date.today, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="bills")
    prescription = relationship("Prescription", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="bill")

from sqlalchemy.dialects.mysql import BIGINT as MySQL_BIGINT

class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)
    bill_id = Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(255), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price_cents = Column(Integer, nullable=False, default=0)
    total_price_cents = Column(Integer, nullable=False, default=0)

    bill = relationship("Bill", back_populates="items")

class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)
    receipt_number = Column(String(50), unique=True, nullable=False)
    bill_id = Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), ForeignKey("bills.id", ondelete="RESTRICT"), nullable=False)
    amount_paid_cents = Column(Integer, nullable=False)
    payment_method = Column(Enum('CARD', 'UPI', 'CASH', 'NET_BANKING', 'INSURANCE', name='pay_method_enum'), default='UPI')
    gateway_transaction_id = Column(String(100), nullable=True)
    gateway_response_payload = Column(JSON, nullable=True)
    payment_status = Column(Enum('SUCCESS', 'FAILED', 'PENDING', 'REVERSED', name='pay_status_enum'), default='SUCCESS')
    settled_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    bill = relationship("Bill", back_populates="receipts")

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    patient_id = Column(BigInteger, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    dose_schedule_id = Column(BigInteger, ForeignKey("dose_schedules.id", ondelete="CASCADE"), nullable=True)
    reminder_type = Column(Enum('DOSE_ALERT', 'BILL_DUE', 'REFILL_ALERT', 'APPOINTMENT', name='rem_type_enum'), default='DOSE_ALERT')
    scheduled_timestamp = Column(DateTime, nullable=False)
    status = Column(Enum('PENDING', 'SENT', 'FAILED', 'DISMISSED', name='rem_status_enum'), default='PENDING')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="reminders")
    dose_schedule = relationship("DoseSchedule", back_populates="reminders")
    delivery_logs = relationship("NotificationDeliveryLog", back_populates="reminder")

    @property
    def is_done(self) -> bool:
        return self.status == 'SENT' or self.status == 'DISMISSED'

    @property
    def medicine_name(self) -> str:
        if self.dose_schedule and self.dose_schedule.prescription_item and self.dose_schedule.prescription_item.medicine:
            return self.dose_schedule.prescription_item.medicine.brand_name
        return "Ibuprofen"

    @property
    def dosage(self) -> str:
        if self.dose_schedule and self.dose_schedule.prescription_item:
            return self.dose_schedule.prescription_item.dosage_quantity
        return "1 pill"

    @property
    def timing_slot(self) -> str:
        if self.dose_schedule and self.dose_schedule.scheduled_time:
            hour = self.dose_schedule.scheduled_time.hour
            if hour < 12:
                return "MORNING"
            elif hour < 17:
                return "AFTERNOON"
            else:
                return "EVENING"
        return "MORNING"

    @property
    def schedule_time(self) -> str:
        if self.dose_schedule and self.dose_schedule.scheduled_time:
            return self.dose_schedule.scheduled_time.strftime("%I:%M %p").lower()
        return "12:00 am"

    @property
    def instructions(self) -> str:
        if self.dose_schedule and self.dose_schedule.prescription_item:
            return self.dose_schedule.prescription_item.instructions or "Take with water"
        return "Take with water"
