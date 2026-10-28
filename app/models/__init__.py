from app.models.user import Role, User, UserRole, Patient, Practitioner, UserSession
from app.models.receipt import Medicine, Prescription, PrescriptionItem, DoseSchedule, Bill, BillItem, Receipt, Reminder
from app.models.verification import AuthOtp, NotificationDeliveryLog, AuditEvent, ConsentRecord, SchemaMigration, BackupHistory
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder

# Legacy/friendly aliases for service compatibility
Doctor = Practitioner
HealthSlip = Bill
ReceiptItem = BillItem
MedicationReminder = Reminder
OtpVerification = AuthOtp
AuditLog = AuditEvent

__all__ = [
    "Role",
    "User",
    "UserSession",
    "UserRole",
    "Patient",
    "Practitioner",
    "Doctor",
    "Medicine",
    "Prescription",
    "PrescriptionItem",
    "DoseSchedule",
    "Bill",
    "BillItem",
    "Receipt",
    "Reminder",
    "HealthSlip",
    "ReceiptItem",
    "MedicationReminder",
    "AuthOtp",
    "NotificationDeliveryLog",
    "AuditEvent",
    "ConsentRecord",
    "SchemaMigration",
    "BackupHistory",
    "OtpVerification",
    "AuditLog",
    "PharmacyMedicineStock",
    "DispenseOrder"
]
