SET foreign_key_checks = 0;

DROP DATABASE IF EXISTS healthslip_prod;
CREATE DATABASE healthslip_prod 
  CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;

USE healthslip_prod;

-- =============================================================================
-- 1. IDENTITY & ACCESS MANAGEMENT
-- =============================================================================

-- Roles table (RBAC)
CREATE TABLE roles (
    id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(32) NOT NULL UNIQUE,          -- e.g., 'ADMIN', 'DOCTOR', 'PHARMACIST', 'PATIENT'
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

-- Core user authentication accounts
CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    uuid CHAR(36) NOT NULL UNIQUE,             -- Public-facing reference ID
    email VARCHAR(191) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    status ENUM('PENDING', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED') NOT NULL DEFAULT 'PENDING',
    is_phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_users_status (status)
) ENGINE=InnoDB;

-- User to Role Mapping
CREATE TABLE user_roles (
    user_id BIGINT UNSIGNED NOT NULL,
    role_id SMALLINT UNSIGNED NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_ur_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_ur_role FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Patient records (HIPAA/Data isolation from general login account)
CREATE TABLE patients (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    uuid CHAR(36) NOT NULL UNIQUE,
    user_id BIGINT UNSIGNED NULL,              -- Nullable for patients registered by hospital staff without an account
    first_name VARCHAR(64) NOT NULL,
    last_name VARCHAR(64) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender ENUM('MALE', 'FEMALE', 'OTHER', 'UNDISCLOSED') NOT NULL,
    blood_group ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'UNKNOWN') DEFAULT 'UNKNOWN',
    emergency_contact_name VARCHAR(128) NULL,
    emergency_contact_phone VARCHAR(20) NULL,
    address_line1 VARCHAR(255) NULL,
    address_line2 VARCHAR(255) NULL,
    city VARCHAR(64) NULL,
    state VARCHAR(64) NULL,
    postal_code VARCHAR(20) NULL,
    country_code CHAR(2) NOT NULL DEFAULT 'IN',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_patient_lookup (last_name, first_name, date_of_birth),
    CONSTRAINT fk_patients_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Clinicians / Doctors profile
CREATE TABLE practitioners (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL UNIQUE,
    license_number VARCHAR(64) NOT NULL UNIQUE,
    specialization VARCHAR(100) NOT NULL,
    department VARCHAR(100) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_practitioner_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- 2. PRESCRIPTIONS & CLINICAL REGISTRATION
-- =============================================================================

-- Master formulary / Medicine registry
CREATE TABLE medicines (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    brand_name VARCHAR(150) NOT NULL,
    generic_name VARCHAR(150) NOT NULL,
    dosage_form ENUM('TABLET', 'CAPSULE', 'SYRUP', 'INJECTION', 'OINTMENT', 'DROPS', 'INHALER', 'OTHER') NOT NULL,
    strength VARCHAR(50) NOT NULL,              -- e.g., '500mg', '10ml'
    manufacturer VARCHAR(150) NULL,
    is_controlled_substance BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_med_names (brand_name, generic_name)
) ENGINE=InnoDB;

-- Prescription master record
CREATE TABLE prescriptions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    uuid CHAR(36) NOT NULL UNIQUE,
    patient_id BIGINT UNSIGNED NOT NULL,
    practitioner_id BIGINT UNSIGNED NOT NULL,
    diagnosis TEXT NULL,
    ocr_raw_text MEDIUMTEXT NULL,              -- Stored transcription if processed via HealthSlip AI OCR
    prescription_image_url VARCHAR(512) NULL,   -- S3/GCS immutable object storage link
    status ENUM('DRAFT', 'ACTIVE', 'DISPENSED', 'CANCELLED', 'EXPIRED') NOT NULL DEFAULT 'ACTIVE',
    issued_date DATE NOT NULL,
    valid_until DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_presc_patient (patient_id, status),
    INDEX idx_presc_practitioner (practitioner_id),
    CONSTRAINT fk_presc_patient FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE RESTRICT,
    CONSTRAINT fk_presc_doc FOREIGN KEY (practitioner_id) REFERENCES practitioners (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Specific prescribed line items
CREATE TABLE prescription_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prescription_id BIGINT UNSIGNED NOT NULL,
    medicine_id BIGINT UNSIGNED NOT NULL,
    dosage_quantity VARCHAR(50) NOT NULL,      -- e.g., '1 tablet'
    frequency VARCHAR(50) NOT NULL,            -- e.g., 'TID' (3 times daily), 'BID'
    route ENUM('ORAL', 'IV', 'IM', 'TOPICAL', 'SUBLINGUAL', 'OPHTHALMIC', 'NASAL') NOT NULL DEFAULT 'ORAL',
    duration_days SMALLINT UNSIGNED NOT NULL,
    instructions VARCHAR(255) NULL,            -- e.g., 'After meals'
    total_quantity_prescribed INT UNSIGNED NOT NULL,
    dispensed_quantity INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT fk_pi_prescription FOREIGN KEY (prescription_id) REFERENCES prescriptions (id) ON DELETE CASCADE,
    CONSTRAINT fk_pi_medicine FOREIGN KEY (medicine_id) REFERENCES medicines (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Adherence & AI Dose reminder schedule generator
CREATE TABLE dose_schedules (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prescription_item_id BIGINT UNSIGNED NOT NULL,
    scheduled_time TIME NOT NULL,               -- e.g., '08:00:00', '13:00:00', '20:00:00'
    meal_relation ENUM('BEFORE_MEAL', 'WITH_MEAL', 'AFTER_MEAL', 'NO_RELATION') DEFAULT 'NO_RELATION',
    dose_amount VARCHAR(30) NOT NULL DEFAULT '1',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id),
    CONSTRAINT fk_ds_item FOREIGN KEY (prescription_item_id) REFERENCES prescription_items (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- 3. BILLING & INVOICING
-- =============================================================================

CREATE TABLE bills (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    invoice_number VARCHAR(50) NOT NULL UNIQUE, -- Human-readable sequence: INV-2026-0001
    patient_id BIGINT UNSIGNED NOT NULL,
    prescription_id BIGINT UNSIGNED NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    subtotal_cents INT UNSIGNED NOT NULL,       -- Stored in smallest currency unit (cents/paise) to prevent floating errors
    tax_cents INT UNSIGNED NOT NULL DEFAULT 0,
    discount_cents INT UNSIGNED NOT NULL DEFAULT 0,
    total_cents INT UNSIGNED NOT NULL,
    status ENUM('ISSUED', 'PARTIALLY_PAID', 'PAID', 'VOID', 'REFUNDED') NOT NULL DEFAULT 'ISSUED',
    due_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_bill_status (status, due_date),
    CONSTRAINT fk_bills_patient FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE RESTRICT,
    CONSTRAINT fk_bills_presc FOREIGN KEY (prescription_id) REFERENCES prescriptions (id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE bill_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    bill_id BIGINT UNSIGNED NOT NULL,
    description VARCHAR(255) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 1,
    unit_price_cents INT UNSIGNED NOT NULL,
    total_price_cents INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_bi_bill FOREIGN KEY (bill_id) REFERENCES bills (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Payment receipts & settlement audit
CREATE TABLE receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_number VARCHAR(50) NOT NULL UNIQUE,
    bill_id BIGINT UNSIGNED NOT NULL,
    amount_paid_cents INT UNSIGNED NOT NULL,
    payment_method ENUM('CARD', 'UPI', 'CASH', 'NET_BANKING', 'INSURANCE') NOT NULL,
    gateway_transaction_id VARCHAR(100) NULL,
    gateway_response_payload JSON NULL,
    payment_status ENUM('SUCCESS', 'FAILED', 'PENDING', 'REVERSED') NOT NULL DEFAULT 'PENDING',
    settled_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_receipt_bill (bill_id),
    INDEX idx_gateway_tx (gateway_transaction_id),
    CONSTRAINT fk_receipts_bill FOREIGN KEY (bill_id) REFERENCES bills (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- =============================================================================
-- 4. NOTIFICATIONS & DISPATCH
-- =============================================================================

-- OTP security & phone/login verifications
CREATE TABLE auth_otps (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    identifier VARCHAR(191) NOT NULL,          -- Phone or email
    otp_hash VARCHAR(255) NOT NULL,
    channel ENUM('SMS', 'WHATSAPP', 'EMAIL') NOT NULL DEFAULT 'SMS',
    attempt_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
    is_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_otp_lookup (identifier, is_consumed, expires_at)
) ENGINE=InnoDB;

-- Message reminders (Medication doses, Bill due alerts)
CREATE TABLE reminders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    patient_id BIGINT UNSIGNED NOT NULL,
    dose_schedule_id BIGINT UNSIGNED NULL,
    reminder_type ENUM('DOSE_ALERT', 'BILL_DUE', 'REFILL_ALERT', 'APPOINTMENT') NOT NULL,
    scheduled_timestamp DATETIME NOT NULL,
    status ENUM('PENDING', 'SENT', 'FAILED', 'DISMISSED') NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_pending_reminders (status, scheduled_timestamp),
    CONSTRAINT fk_rem_patient FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE CASCADE,
    CONSTRAINT fk_rem_dose FOREIGN KEY (dose_schedule_id) REFERENCES dose_schedules (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Delivery status logs
CREATE TABLE notification_delivery_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    reminder_id BIGINT UNSIGNED NULL,
    recipient VARCHAR(191) NOT NULL,
    provider ENUM('TWILIO', 'AWS_SNS', 'GUPSHUP', 'SENDGRID') NOT NULL,
    provider_message_id VARCHAR(128) NULL,
    delivery_status ENUM('QUEUED', 'SENT', 'DELIVERED', 'UNDELIVERED', 'FAILED') NOT NULL,
    failure_reason VARCHAR(255) NULL,
    dispatched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_ndl_reminder (reminder_id),
    INDEX idx_ndl_status (delivery_status),
    CONSTRAINT fk_ndl_reminder FOREIGN KEY (reminder_id) REFERENCES reminders (id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- =============================================================================
-- 5. SECURITY & OPERATIONS
-- =============================================================================

-- Immutable audit logs for compliance (HIPAA / DPDP Act)
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    actor_user_id BIGINT UNSIGNED NULL,        -- NULL if triggered by background system daemon
    action VARCHAR(64) NOT NULL,               -- e.g., 'READ_PRESCRIPTION', 'EXPORT_BILLING'
    resource_type VARCHAR(64) NOT NULL,        -- e.g., 'patients', 'prescriptions'
    resource_id VARCHAR(64) NOT NULL,
    ip_address VARCHAR(45) NULL,               -- IPv4 or IPv6 format
    user_agent VARCHAR(255) NULL,
    payload_before JSON NULL,
    payload_after JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_audit_resource (resource_type, resource_id),
    INDEX idx_audit_actor (actor_user_id, created_at),
    CONSTRAINT fk_audit_user FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Explicit Patient Consent Records
CREATE TABLE consent_records (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    patient_id BIGINT UNSIGNED NOT NULL,
    consent_purpose ENUM('AI_ANALYSIS', 'SMS_REMINDERS', 'THIRD_PARTY_SHARING', 'TELEMEDICINE') NOT NULL,
    is_granted BOOLEAN NOT NULL DEFAULT FALSE,
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP NULL,
    signature_hash VARCHAR(128) NULL,          -- Digital or OTP verification digest
    PRIMARY KEY (id),
    INDEX idx_patient_consent (patient_id, consent_purpose),
    CONSTRAINT fk_consent_patient FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Database schema migration tracking
CREATE TABLE schema_migrations (
    version VARCHAR(128) NOT NULL,
    description VARCHAR(255) NOT NULL,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms INT UNSIGNED NOT NULL,
    PRIMARY KEY (version)
) ENGINE=InnoDB;

-- Scheduled backup/recovery telemetry records
CREATE TABLE backup_history (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    backup_file_name VARCHAR(255) NOT NULL,
    backup_type ENUM('FULL', 'INCREMENTAL', 'SNAPSHOT') NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    checksum_sha256 CHAR(64) NOT NULL,
    status ENUM('STARTED', 'COMPLETED', 'FAILED') NOT NULL,
    storage_destination VARCHAR(255) NOT NULL, -- e.g., 's3://healthslip-backups/daily/...'
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

SET foreign_key_checks = 1;
