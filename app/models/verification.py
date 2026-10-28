import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, Boolean, Enum, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class AuthOtp(Base):
    __tablename__ = "auth_otps"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    identifier = Column(String(191), nullable=False, index=True)
    otp_hash = Column(String(255), nullable=False)
    channel = Column(Enum('SMS', 'WHATSAPP', 'EMAIL', name='otp_channel_enum'), default='SMS')
    attempt_count = Column(Integer, default=0)
    is_consumed = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class NotificationDeliveryLog(Base):
    __tablename__ = "notification_delivery_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    reminder_id = Column(BigInteger, ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True)
    recipient = Column(String(191), nullable=False)
    provider = Column(Enum('TWILIO', 'AWS_SNS', 'GUPSHUP', 'SENDGRID', name='provider_enum'), default='TWILIO')
    provider_message_id = Column(String(128), nullable=True)
    delivery_status = Column(Enum('QUEUED', 'SENT', 'DELIVERED', 'UNDELIVERED', 'FAILED', name='deliv_status_enum'), default='SENT')
    failure_reason = Column(String(255), nullable=True)
    dispatched_at = Column(DateTime, default=datetime.datetime.utcnow)

    reminder = relationship("Reminder", back_populates="delivery_logs")

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    payload_before = Column(JSON, nullable=True)
    payload_after = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    patient_id = Column(BigInteger, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    consent_purpose = Column(Enum('AI_ANALYSIS', 'SMS_REMINDERS', 'THIRD_PARTY_SHARING', 'TELEMEDICINE', name='consent_purpose_enum'), nullable=False)
    is_granted = Column(Boolean, default=False)
    granted_at = Column(DateTime, default=datetime.datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    signature_hash = Column(String(128), nullable=True)

class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version = Column(String(128), primary_key=True)
    description = Column(String(255), nullable=False)
    executed_at = Column(DateTime, default=datetime.datetime.utcnow)
    execution_time_ms = Column(Integer, nullable=False, default=0)

class BackupHistory(Base):
    __tablename__ = "backup_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    backup_file_name = Column(String(255), nullable=False)
    backup_type = Column(Enum('FULL', 'INCREMENTAL', 'SNAPSHOT', name='backup_type_enum'), default='FULL')
    size_bytes = Column(BigInteger, nullable=False, default=0)
    checksum_sha256 = Column(String(64), nullable=False)
    status = Column(Enum('STARTED', 'COMPLETED', 'FAILED', name='backup_status_enum'), default='COMPLETED')
    storage_destination = Column(String(255), nullable=False)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

# Aliases
AuditLog = AuditEvent
OtpVerification = AuthOtp
