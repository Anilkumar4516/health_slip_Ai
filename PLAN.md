# HealthSlip AI - Real-World Indian Medical Store Pilot Implementation Plan

This plan outlines the architecture, database migrations, security hardening, and step-by-step roadmap to prepare HealthSlip AI for real-world pilot deployments in Indian retail medical stores and community pharmacies (Jan Aushadhi Kendras / Seva Stores).

---

## 1. Architectural Overview & Changes

### Task 1: Authentication, Stores & Roles
- **Roles**: Strict RBAC supporting `DOCTOR`, `PHARMACIST`, `PATIENT`, and `ADMIN`.
- **JWT & Password Security**:
  - Dual-token architecture: Short-lived access JWT (e.g. 15-30 mins) + persistent refresh token (7-30 days) with token revocation in `user_sessions`.
  - Upgraded hashing with PBKDF2-SHA256/bcrypt and constant-time comparison, preserving backwards compatibility for seeded demo accounts.
- **Store / Pharmacy Model**:
  - `pharmacies` / `stores` table: `id`, `name`, `drug_license_number` (DL 20-B / 21-B), `gstin`, `address`, `city`, `state`, `postal_code`, `phone`, `email`, `created_at`.
  - Pharmacist user accounts linked via `store_id` (ForeignKey) and profile.
- **WebSocket Rooms**:
  - Secure `/ws/live` connection requiring token authentication.
  - Connection isolation: Pharmacy staff join room `store_{store_id}`; Doctors broadcast prescriptions to designated or selected store; Patients receive only their own verification/adherence events.

### Task 2: Real & Pluggable OTP System
- **Provider Interface**: `SMSProviderInterface` with pluggable adapters:
  - `Fast2SMSProvider` (Quick SMS / DLT transactional route in India).
  - `MSG91Provider` (DLT Flow route with Template ID & Auth Key).
  - `ConsoleMockSMSProvider` (Clean console logger strictly for development & automated tests).
- **Environment Isolation**:
  - When `ENVIRONMENT == "production"` or `ENV == "production"`, completely disable dev sandbox OTP returns in HTTP response payloads and remove sandbox UI toast helpers.
- **Rate Limiting & Lockout**:
  - 60s cooldown per phone, 3-attempt lockout with SHA-256 HMAC verification.
  - IP-based rate limiting (max 5 requests/hr per IP) and phone-based rate limiting (max 3 requests/hr per phone).

### Task 3: Pharmacy Dispensing Workflow
- **Verification First**:
  - Scan/Lookup verifies HMAC signature (`calculate_verification_hash`) before returning medication slip details to the pharmacist.
- **Full & Partial Dispensing**:
  - Line-item tracking: `prescribed_quantity`, `dispensed_quantity`, `remaining_quantity`.
  - Transaction-level row lock (`SELECT ... FOR UPDATE`) on the prescription and dispense order to strictly prevent race conditions and cross-store double dispensing.
  - Refill validation: `refills_allowed` and `refills_remaining` with `valid_until` date (default 30 days). Expired or exhausted prescriptions cannot be refilled.
- **Drug Schedule Compliance (Drugs and Cosmetics Act, 1940)**:
  - Categorize medications with `drug_schedule`: `OTC`, `SCHEDULE_H`, `SCHEDULE_H1`, `SCHEDULE_X`.
  - Require explicit pharmacist confirmation checkbox and audit logging (pharmacist name, doctor registration number, batch number) for Schedule H/H1/X drugs.
- **Jan Aushadhi Generic Substitution**:
  - Always presented as a recommendation with price savings; requires pharmacist review and confirmation before applying substitute; records substitution in AuditLog.

### Task 4: Inventory & Billing (FEFO + GST)
- **Batch Inventory**:
  - `store_inventory`: `id`, `store_id`, `brand_name`, `generic_name`, `batch_no`, `expiry_date`, `quantity`, `mrp`, `purchase_price`, `hsn_code`, `gst_rate`, `drug_schedule`.
  - Automatic low-stock (`<= reorder_level`) and near-expiry (`<= 90 days`) alerts.
- **FEFO (First-Expiry-First-Out) Auto-Decrement**:
  - On dispensing, automatically decrement available stock from batches with the earliest expiration date.
- **CSV Data Migration**:
  - Bulk import and export endpoints for medical stores migrating from legacy billing software.
- **GST-Compliant Tax Invoices**:
  - Generate GST invoice PDF via ReportLab including Store Name, GSTIN, DL Numbers, HSN codes, Batch, Expiry, CGST/SGST/IGST breakdown, and Total in INR (`₹`).

### Task 5: AI Safety & Patient Privacy
- **Draft Safeguard**:
  - Every AI-parsed slip is tagged as `DRAFT`. Slips can never be auto-issued; a licensed doctor must review, adjust, and approve.
- **Patient De-Identification**:
  - Clinical notes scrubbed of PHI (patient full names, phone numbers, addresses, emails) before transmitting to external Gemini API.
  - External AI calls can be toggled on/off via `ENABLE_EXTERNAL_AI=False`. Heuristic clinical NLP engine remains the default reliable offline engine.
- **Edge-Case Unit Testing**:
  - Tests for uncommon dosage formats, fractions, complex trade names, and pediatric drops.

### Task 6: Real-Time Scaling (Redis Pub/Sub)
- **Distributed Event Broadcaster**:
  - Redis Pub/Sub backend for multi-worker / multi-container deployments (Gunicorn/Uvicorn), broadcasting messages across nodes.
  - Automatic fallback to in-memory event queue for local single-process dev/test.
  - Add Redis 7 service to `docker-compose.yml`.
- **Frontend Heartbeat**:
  - Periodic ping/pong and resilient exponential-backoff WebSocket reconnection.

### Task 7: Offline-First for Rural Outposts
- **Idempotent Queue**:
  - Client-generated transaction UUID (`client_sync_id`).
  - Cache dispensing transactions locally in localStorage/IndexedDB.
  - Require server sync connection for the final cryptographic dispense confirmation so disparate physical stores cannot double-dispense offline.
  - Visual status pill: `Online` vs `Offline (N queued items)`.

### Task 8: Security, Governance & DPDP Act 2023
- **Secret & Key Management**:
  - Startup check fails fast if `ENVIRONMENT=production` and default keys or missing DB credentials are detected.
  - HMAC key versioning (`key_id: "v1"`) allowing zero-downtime key rotation.
- **Security Headers & CORS**:
  - Security headers middleware (`CSP`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `HSTS`).
  - Restricted CORS origin policy in production.
- **Field-Level Encryption**:
  - Sensitive patient details (e.g. emergency contacts, address line) encrypted at rest using AES-256-GCM / Fernet.
- **India DPDP Act 2023**:
  - Patient consent capture (`POST /api/patients/{id}/consent`).
  - "Right to be Forgotten" (`POST /api/patients/{id}/erase-data`) with retention compliance rules for prescriptions.
  - Dedicated Privacy Policy page.
- **Comprehensive Audit Trail**:
  - Record login, OTP, issue, view, dispense, and delete actions with actor ID, IP address, and timestamps.

### Task 9: DevOps & Production Readiness
- **Database Engine**:
  - Enforce MySQL in production without SQLite fallback.
  - Alembic database migration environment and versioned scripts.
- **Monitoring & CI/CD**:
  - Health (`/api/health`) & Readiness (`/api/ready`) probes.
  - Structured JSON/key-value logging.
  - GitHub Actions CI workflow (`.github/workflows/ci.yml`) running test suites on push.
  - Comprehensive Pilot Deployment Guide in `README.md`.

---

## 2. Identified Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Breaking Existing Tests** | High | Keep existing route contracts and endpoints intact. Extend schemas and services with safe optional defaults. Run test suites after each step. |
| **Double-Dispensing Across Stores** | High | Use database-level row locking (`with_for_update()`) inside atomic transactions combined with cryptographic lock hashes. |
| **MySQL vs SQLite Test Discrepancies** | Medium | Maintain SQLAlchemy ORM compatibility; SQLite handles unit tests gracefully while MySQL handles production concurrency. |
| **DLT Registration Delays in India** | Medium | Pluggable SMS architecture allows instant local pilot testing via Mock/Dev provider while production easily switches to Fast2SMS/MSG91 with DLT template ID. |
| **Accidental PHI Leakage to LLMs** | High | Pre-request regex de-identification scrubber; disable external AI calls by default unless explicitly configured. |

---

## 3. Implementation Steps

1. **Step 1: Auth & Store Models & Roles** -> Add Store model, DOCTOR/PHARMACIST/PATIENT/ADMIN roles, JWT access+refresh tokens, and store-linked pharmacist. Run tests.
2. **Step 2: Real OTP & Security Rate Limits** -> Implement pluggable SMS provider (Fast2SMS, MSG91, Mock), production sandbox masking, per-IP and per-phone rate limiting. Run tests.
3. **Step 3: Pharmacy Dispensing Workflow** -> Verify HMAC before lookup, row-level `with_for_update` locking, partial dispensing, refills validity, Schedule H/H1/X confirmation, and generic substitution approval. Run tests.
4. **Step 4: Inventory, FEFO & GST Billing** -> Add Store Inventory model, FEFO stock reduction, CSV import/export, and ReportLab GST invoice PDF. Run tests.
5. **Step 5: AI Safety & De-identification** -> AI drafts, doctor approval workflow, patient PII scrubber, and edge-case dosage parsing tests. Run tests.
6. **Step 6: Real-Time Scaling & Redis** -> Redis Pub/Sub WebSocket broadcaster with in-memory fallback, docker-compose update, and frontend ping/pong reconnect. Run tests.
7. **Step 7: Offline-First Rural Sync** -> Idempotent client sync UUIDs, dispense confirmation check, and UI offline/sync indicators. Run tests.
8. **Step 8: Security, DPDP Act & Encryption** -> Startup secret validation, HMAC key rotation, security headers, Fernet field encryption, consent & erasure endpoints, and privacy policy. Run tests.
9. **Step 9: DevOps & CI/CD** -> Alembic migrations, readiness endpoint, structured logging, GitHub Actions workflow, and README pilot guide. Run tests.
