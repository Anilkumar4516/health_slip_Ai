# HealthSlip AI 🩺✨
### Enterprise Medical Billing, Tamper-Proof Prescription Dispatch & Indian Retail Pharmacy Pilot Platform
**Built for Indian Medical Stores (Urban Smart POS & Rural Seva Kendras) with FastAPI, SQLAlchemy 2.0, MySQL 8.0, Redis 7, Vanilla JS, and WebSockets.**

---

## 🌟 Executive Overview & Pilot Architecture

**HealthSlip AI** is a production-grade clinical dispensing, billing, and patient verification platform designed specifically for the unique operational challenges of Indian retail pharmacies and clinics. It bridges the gap between rapid doctor clinical note writing and tamper-proof dispensing across both high-velocity urban smart pharmacies and resource-constrained rural Seva Kendras.

```
                           ┌────────────────────────┐
                           │   Doctor Consultation  │
                           │  Clinical AI (DRAFT)   │
                           └───────────┬────────────┘
                                       │ (Explicit Approval)
                                       ▼
                     ┌────────────────────────────────────┐
                     │   HMAC-SHA256 Cryptographic Seal   │
                     │  Key Versioning: 'v1' (Rotatable)   │
                     └─────────────────┬──────────────────┘
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        ▼                                                             ▼
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│   Urban Smart Pharmacy (POS)    │                 │   Rural Seva Medical Kendra     │
│ - Live Prescription Dispatch    │                 │ - Jan Aushadhi Cost Saver       │
│ - FEFO Inventory Decrement      │                 │ - Telugu Vernacular TTS Audio   │
│ - Partial/Full Item Dispense    │                 │ - 2G Keypad SMS Slip (<160 ch)  │
│ - Schedule H/H1/X Confirmations │                 │ - Idempotent Offline Sync (UUID)│
│ - GST-Compliant Tax Invoice PDF │                 │ - Double-Dispensing Lock Check  │
└────────────────┬────────────────┘                 └────────────────┬────────────────┘
                 │                                                   │
                 └────────────────────────┬──────────────────────────┘
                                          ▼
                      ┌───────────────────────────────────────┐
                      │    Patient Portal & Verification      │
                      │ - Trai/DLT SMS Gateway (MSG91/Fast2SMS│
                      │ - Fernet AES-128 Encrypted at Rest    │
                      │ - India DPDP Act 2023 Consent/Erasure │
                      │ - Vernacular Telugu Adherence Tracker │
                      └───────────────────────────────────────┘
```

---

## 🚀 Key Pilot Modules & Capabilities

### 1. 🏪 Retail Pharmacy Dispensing Workflow (Tasks 3 & 4)
- **HMAC Verification Prior to Display**: The dispensing terminal cryptographically validates the prescription signature (`slip_number + patient_phone + grand_total + date`) against the active HMAC key version (`v1`) before displaying clinical records.
- **Full & Line-Item Partial Dispensing**: Dispense individual medicines, adjust quantity delivered, track `dispensed_quantity`, and maintain accurate dispensing records.
- **Anti-Double-Dispensing Database Row Locks**: Employs SQLAlchemy `with_for_update()` database row-level locking during the dispense transaction, mathematically preventing two stores (or two browser tabs) from concurrently dispensing the same prescription.
- **Schedule H / H1 / X Compliance**: Restricted drugs (e.g., Alprazolam, Zolpidem, Antibiotics) trigger statutory warning banners, requiring pharmacist confirmation and recording the pharmacist ID, timestamp, and store ID in `audit_events`.
- **Refill Tracking & Validity Expiry**: Enforces doctor-prescribed `refills_allowed` and `refills_remaining` with a default 30-day validity window.
- **FEFO (First-Expiry-First-Out) Auto-Decrement**: Automatically identifies and decrements stock from the batch closest to expiration date, alerting staff if stock is low (< 10 units) or near expiration (< 60 days).
- **GST-Compliant Tax Invoices (PDF)**: Generates legal Indian pharmacy tax invoices via ReportLab detailing Pharmacy Drug License Numbers (Form 20-B/21-B), GSTIN, HSN codes, and 50/50 CGST + SGST tax splits.
- **CSV Inventory Import / Export**: Instant two-way CSV migration (`/api/pharmacy/inventory/export-csv` and `/api/pharmacy/inventory/import-csv`) enabling pharmacies to seamlessly sync with legacy billing software.

### 2. 🌾 Rural Seva Medical Store Mode (Accessibility & Affordability)
- **Jan Aushadhi Generic Substitution Calculator**: Automatically identifies government-certified bio-equivalent generic salts (Pradhan Mantri Bhartiya Janaushadhi Pariyojana), showing rural families 75% to 85% price savings with pharmacist confirmation.
- **Authentic Telugu Vernacular Audio Explainer (TTS)**: Web Speech API synthesized in natural Telugu (`te-IN`) and English, reading dosage instructions aloud for elderly and rural patients alongside visual glyphs (🌅 ఉదయం, ☀️ మధ్యాహ్నం, 🌙 రాత్రి, 🍽️ భోజనం తర్వాత).
- **2G Keypad SMS Slip**: Generates ultra-concise GSM-7 compliant SMS slips (< 160 characters) formatted specifically for basic feature phones.
- **Offline-First Synchronization**: Caches offline transactions in local storage with client-generated UUIDs (`client_sync_id`). While bills can be pre-staged offline, final dispensing confirmation strictly requires an online verification handshake to prevent dual-store fraud.

### 3. 🤖 AI Clinical Safety Guardrails (Task 5)
- **Mandatory DRAFT Status**: Every AI-parsed prescription is strictly flagged as `DRAFT`. Slips cannot be issued to pharmacies or patients until a licensed doctor reviews, edits, and explicitly clicks "Approve & Issue".
- **Patient PII Scrubber**: Before any clinical notes are passed to external LLMs (Google Gemini Flash), patient names, phone numbers, email addresses, and street addresses are scrubbed.
- **Offline Heuristic NLP Fallback**: When external AI is toggled off (`ENABLE_EXTERNAL_AI=False`), a built-in medical rule-based engine parses diagnoses, line items, and complex dosages offline with zero cloud dependencies.
- **Advanced Dosage Parsing**: Robust regex handlers support fractions (e.g., `1/2 tab`), pediatric drops (`5 drops`), milliliter volumes (`10 ml`), and medical abbreviations (`OD`, `BID`, `TID`, `QID`, `SOS`, `HS`).

### 4. 🔐 Authentication, Roles & WebSocket Rooms (Task 1)
- **Role-Based Access Control (RBAC)**: Support for `DOCTOR`, `PHARMACIST`, `PATIENT`, and `ADMIN`.
- **PBKDF2-SHA256 & JWT Rotation**: Staff authenticate via phone/email and password, receiving a short-lived access JWT (60m) paired with an automated refresh token rotation endpoint (`/api/auth/refresh-token`).
- **Store-Isolated WebSocket Hub (`/ws/live?token=...`)**: Real-time push events are scoped to specific rooms by `store_id` (urban pharmacy vs rural Seva Kendra) and `patient_phone`. Real-time scaling is backed by Redis 7 Pub/Sub with an automatic in-memory fallback.

### 5. 📱 Trai / DLT Pluggable SMS Gateway & Rate Limiting (Task 2)
- **Pluggable SMS Architecture**: Clean provider abstraction (`app/services/sms_provider.py`) supporting `Fast2SMSProvider`, `MSG91Provider` (DLT template compliant), and a local `ConsoleMockSMSProvider`.
- **Anti-Abuse Protections**:
  - 60-second cooldown per phone number.
  - 3-attempt lockout per OTP challenge.
  - Per-IP rate limiting (15 requests/hour) and per-phone rate limiting (5 requests/hour).
  - Suppression of sandbox OTPs in production (`DEV_OTP_SANDBOX_MODE=False`).

### 6. 🛡️ India DPDP Act 2023 & Cryptographic Privacy (Task 8)
- **Encryption at Rest**: Patient demographics (phone, email, street address) are encrypted at rest using AES-128 via Fernet with `enc$` prefixed tokens.
- **HMAC Key Versioning**: Prescriptions store their `key_id` (e.g. `v1`), enabling seamless key rotation without invalidating existing signed slips.
- **Statutory Consent & Right to Erasure**:
  - `POST /api/patients/{id}/consent`: Captures auditable consent purpose, timestamp, and IP address.
  - `POST /api/patients/{id}/erase-data`: Allows patients to execute their statutory Right to Erasure under DPDP Act 2023 Section 12, anonymizing identifiers while preserving financial audit records.
  - `/privacy`: Dedicated statutory Privacy Policy and Data Principal Charter.
- **Production Fail-Fast**: Application refuses to boot in production if default secrets, weak database passwords, or SQLite fallbacks are detected.

### 7. 🛠️ DevOps, Migrations & Observability (Task 9)
- **Production MySQL Enforcement**: Strict prohibition of SQLite fallback when `ENVIRONMENT=production`.
- **Alembic Migrations**: Fully configured database version tracking (`alembic upgrade head`).
- **Structured JSON Logging**: RFC-3339 formatted structured JSON logs with correlation IDs (`X-Request-ID`), response latencies (`duration_ms`), and status codes.
- **Health & Readiness Probes**:
  - `/api/health`: Liveness probe for uptime monitoring.
  - `/api/ready`: Readiness probe verifying live MySQL connection and Redis broker status.
- **Continuous Integration**: GitHub Actions workflow (`.github/workflows/ci.yml`) spinning up MySQL 8.0 and Redis 7 containers and executing 39 automated tests on every push.

---

## 👥 Pre-Seeded Pilot Accounts & Test Credentials

The database automatically seeds standard pilot accounts upon initial launch:

| Role | Username / Email | Phone | Password | Assigned Facility / Store |
|---|---|---|---|---|
| **Doctor** | `dr.rao@healthslip.ai` | `+919876500001` | `Doctor@2026` | HealthSlip AI Multi-Specialty Clinic & Seva Kendra (TSMC-2024-8841) |
| **Pharmacist (Urban)** | `pharmacist.urban@healthslip.ai` | `+919876500002` | `Pharmacist@2026` | Store 1: HealthSlip Central Pharmacy (DL: 20-B/TS/48912) |
| **Pharmacist (Rural)** | `pharmacist.rural@healthslip.ai` | `+919876500003` | `Pharmacist@2026` | Store 2: Rural Jan Aushadhi Seva Kendra (DL: 20-B/TS/98214) |
| **Admin** | `admin@healthslip.ai` | `+919876500099` | `Admin@2026` | System Administration |
| **Patient (Demo)** | `rajesh.kumar@example.com` | `+919876543210` | `Patient@2026` | Patient (OTP access or password) |

---

## 🚀 Step-by-Step Pilot Setup & Local Execution Guide

### Prerequisites
- Python 3.11+
- MySQL 8.0 (or local SQLite for dev testing)
- Optional: Redis 7 (for multi-worker WebSocket scaling)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/health_slip_Ai.git
cd health_slip_Ai
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure your database credentials and secret key are set.

### 3. Run Database Migrations
```bash
python -m alembic upgrade head
```

### 4. Start the Application Server
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8005 --reload
```
Open **[http://127.0.0.1:8005](http://127.0.0.1:8005)** in your web browser.

### 5. Run the Automated Test Suite
```bash
python -m pytest
```
*Executes all 39 test cases covering authentication, AI parsing, FEFO dispensing, OTP security, DPDP compliance, and readiness probes.*

---

## 🐳 Docker Compose Deployment (1-Click Production Stack)

To run the complete production stack (FastAPI web server, MySQL 8.0 with persistent storage, and Redis 7 pub/sub):

```bash
docker compose up -d --build
```

To view logs:
```bash
docker compose logs -f app
```

To stop:
```bash
docker compose down
```

---

## 📋 Production Deployment & Go-Live Checklist

Before deploying HealthSlip AI to an Indian medical store pilot, ensure the following checklist items are completed:

- [ ] **1. TRAI DLT Registration (SMS Gateways)**
  - Register the business entity on the telecom DLT portal (e.g. Jio DLT, Vilpower, Airtel).
  - Register Header / Sender ID (e.g. `HLTSLP` or `HLTPHM`).
  - Submit OTP and Prescription SMS templates for approval and paste the `DLT_TE_ID` into `.env`.
- [ ] **2. Production Environment Settings**
  - Set `ENVIRONMENT=production` in `.env`.
  - Set `DEBUG=False`.
  - Set `DEV_OTP_SANDBOX_MODE=False` (ensures OTPs are never exposed in responses or UI banners).
  - Set `FALLBACK_TO_SQLITE=False` (ensures strict MySQL usage).
- [ ] **3. Cryptographic Secret Keys Generation**
  - Generate a 64-character random string for `SECRET_KEY`:
    ```bash
    python -c "import secrets; print(secrets.token_hex(32))"
    ```
  - Generate a 32-byte URL-safe base64 key for `DATA_ENCRYPTION_KEY`:
    ```bash
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```
- [ ] **4. MySQL 8.0 Hardening**
  - Create a dedicated non-root database user with access limited to `healthslip_prod`.
  - Ensure SSL/TLS is enabled for database connections (`ssl_ca` in production).
  - Schedule automated daily MySQL backups with checksum verification.
- [ ] **5. Domain, CORS & Reverse Proxy (SSL/TLS)**
  - Place HealthSlip AI behind Nginx, Caddy, or Cloudflare with a valid Let's Encrypt SSL certificate.
  - Configure `CORS_ALLOWED_ORIGINS` to only permit authorized pharmacy POS domains (e.g. `https://pos.yourstore.com`).
- [ ] **6. Store Inventory & DL Verification**
  - Configure the store's official State Pharmacy Council Drug License Numbers (Form 20-B and 21-B) and GSTIN in the database.
  - Export inventory template via `/api/pharmacy/inventory/export-csv`, populate actual batches and expiry dates, and import via `/api/pharmacy/inventory/import-csv`.

---

## ⚖️ Regulatory & Legal Compliance Notes

- **Drugs and Cosmetics Act, 1940 & Rules, 1945**: Schedule H, H1, and X medications require a valid prescription and confirmation logging before dispensing. HealthSlip AI enforces explicit confirmation and logs the pharmacist user ID and timestamp in `audit_events`.
- **Digital Personal Data Protection Act (DPDP Act 2023)**: HealthSlip AI implements consent capturing (`/api/patients/{id}/consent`), Right to Erasure (`/api/patients/{id}/erase-data`), AES-128 encryption at rest, and publishes a statutory Privacy Policy (`/privacy`).
- **Pradhan Mantri Bhartiya Janaushadhi Pariyojana (PMBJP)**: Generic substitution calculations are provided strictly as advisory suggestions to the pharmacist and patient and require explicit pharmacist confirmation prior to dispensing.

---

## 📄 License
This project is licensed under the MIT License. Designed for healthcare workers, medical professionals, and pharmacists across India.
