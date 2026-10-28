import datetime
import uuid
from sqlalchemy import Column, BigInteger, SmallInteger, String, DateTime, Date, Enum, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Role(Base):
    __tablename__ = "roles"

    id = Column(SmallInteger, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    users = relationship("UserRole", back_populates="role")

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = Column(String(191), unique=True, nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False, default="sha256$default$hash")
    status = Column(Enum('PENDING', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED', name='user_status_enum'), default='ACTIVE')
    is_phone_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    roles = relationship("UserRole", back_populates="user")
    practitioner = relationship("Practitioner", back_populates="user", uselist=False)
    patient = relationship("Patient", back_populates="user", uselist=False)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

from sqlalchemy.dialects.mysql import BIGINT as MySQL_BIGINT

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)
    session_token = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger().with_variant(MySQL_BIGINT(unsigned=True), "mysql"), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")

class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(SmallInteger, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users")

class Patient(Base):
    __tablename__ = "patients"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    first_name = Column(String(64), nullable=False)
    last_name = Column(String(64), nullable=False)
    date_of_birth = Column(Date, nullable=False, default=datetime.date(1996, 5, 12))
    gender = Column(Enum('MALE', 'FEMALE', 'OTHER', 'UNDISCLOSED', name='patient_gender_enum'), default='MALE')
    blood_group = Column(Enum('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'UNKNOWN', name='blood_group_enum'), default='O+')
    emergency_contact_name = Column(String(128), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(64), nullable=True, default="Medical Arts District")
    state = Column(String(64), nullable=True, default="CA")
    postal_code = Column(String(20), nullable=True, default="90210")
    country_code = Column(String(2), default="IN")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="patient")
    prescriptions = relationship("Prescription", back_populates="patient")
    bills = relationship("Bill", back_populates="patient")
    reminders = relationship("Reminder", back_populates="patient")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age(self) -> int:
        if not self.date_of_birth:
            return 28
        today = datetime.date.today()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))

    @property
    def phone(self) -> str:
        return self.user.phone_number if self.user else "+1 555-019-2834"

class Practitioner(Base):
    __tablename__ = "practitioners"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    license_number = Column(String(64), unique=True, nullable=False)
    specialization = Column(String(100), nullable=False, default="General & Internal Medicine")
    department = Column(String(100), nullable=True, default="Clinical Diagnostics")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="practitioner")
    prescriptions = relationship("Prescription", back_populates="practitioner")

    @property
    def name(self) -> str:
        return f"Dr. {self.specialization}" if not self.user else f"Dr. Minh Nguyen, M.D."

    @property
    def clinic_name(self) -> str:
        return f"HealthSlip AI Medical Center ({self.department or 'Care Unit'})"
