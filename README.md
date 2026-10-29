# HealthSlip AI 🩺✨
### AI-Assisted Medical Receipt Generation and OTP-Based Patient Verification System

**HealthSlip AI** is a medical billing, prescription slip generation, and cryptographic patient verification platform built with **Python (FastAPI)**, **MySQL / SQLAlchemy**, **Pydantic**, **HTML5**, **CSS3**, and **vanilla JavaScript**.

Inspired by modern clinical apps, HealthSlip AI bridges the gap between fast clinical note writing for doctors and tamper-proof, privacy-conscious digital receipts and medication schedules for patients.

---

## 🌟 Key Features

### 1. 🤖 AI-Assisted Medical Receipt & Prescription Builder
- **Unstructured Clinical Notes to Structured Receipt**: Doctors can write or paste clinical notes (or click sample templates like *Migraine & Rhinitis*, *Bronchitis*, *Hypertension*).
- **Clinical Entity & Dosage Parser**: Automatically extracts diagnoses, symptoms, line items (Consultations, Medications, Diagnostics/Lab Tests, Procedures), and patient schedules.
- **AI Safety & Interaction Checks**: Flags drug contraindications and dosage precautions (e.g., taking NSAIDs with food to prevent gastric irritation, completing antibiotic courses).
- **Dual-Engine Design**: Uses Google Gemini Flash API when an API key is provided, or seamlessly runs an intelligent clinical NLP heuristic engine offline.

### 2. 🔐 OTP-Based Patient Verification System (HIPAA Privacy-Alike)
- **Zero Plaintext Storage**: OTPs are salted and hashed using **HMAC-SHA256** before database storage.
- **Rate-Limiting & Brute-Force Lockout**: Enforces a 60-second cooldown between requests and locks out after 3 failed attempts.
- **Cryptographic Access Token**: Upon verification, an access token is issued to view private health slips and medical invoices.
- **Dev Sandbox Mode**: In development mode, the generated OTP is displayed in a dev toast banner for instant testing.

### 3. 🛡️ Cryptographic Tamper-Proof Verification (HMAC-SHA256) & QR Codes
- Every issued health slip is sealed with a digital signature: `HMAC-SHA256(slip_number + patient_phone + grand_total + date, SECRET_KEY)`.
- Physical and digital receipts embed an official QR code linking to public verification.
- **Privacy-Preserving Public Scan**: Verifies receipt authenticity, doctor name, and hospital registration without exposing sensitive patient health details (name is masked e.g. `M*** N*****`).

### 4. 📱 Interactive Patient Mobile App (Faithful to Design Screenshot)
- **Patient Profile**: Friendly greeting (`Good day, Minh`), search bar, and notification bell.
- **Interactive Calendar Ribbon**: Horizontally scrollable calendar selector (`August 2022`, `Sun 21`, `Mon 22`...).
- **Medication Reminders & Adherence Tracker**:
  - Morning (`12:00 am`): *Ibuprofen 1 pill* -> `[DONE]`
  - After lunch: *Ibuprofen metisylat 1 pill* -> `[DONE]`
  - Afternoon: *Ibuprofen 1 pill* -> `[DONE]`
- **Real-Time Adherence Calculation**: Updates adherence % dynamically when doses are checked off.

### 5. 📄 Official PDF Receipt Generator
- Generates professional medical invoices via **ReportLab** with hospital branding, physician license, patient demographics, itemized table, dosage schedules, QR code, and HMAC seal.

### 6. ⚡ Real-Time WebSockets & Inflow Synchronization
- **Live Bidirectional WebSockets (`/ws/live`)**: Connects doctors, pharmacies, and patients with instant push notifications (zero manual polling).
- **Audio Chime & Live Toast Banners**: Synthesizes audible chimes and instant notifications upon new prescription arrivals.
- **Dynamic Counters**: Live unread badges update immediately when a doctor issues a slip.

### 7. 🏪 Urban & Rural Medical Store Hub (Dual-Mode)
- 🏢 **Urban Smart Pharmacy Mode (High-Velocity POS)**:
  - **Live Dispatch Queue**: Real-time incoming prescriptions direct from clinical doctors.
  - **Inventory & Batch Tracking**: Live stock counts, reorder warnings, and quick restock buttons.
  - **Cryptographic Anti-Double Dispensing Lock**: Seals dispensed prescriptions with HMAC-SHA256, mathematically preventing duplicate dispensing across different medical stores.
- 🌾 **Rural Seva Medical Store Mode (Affordability & Accessibility)**:
  - **Jan Aushadhi Generic Medicine Cost Saver**: Automatically identifies government-certified bio-equivalent generic salts for expensive branded drugs, calculating 70% to 85% price savings for rural families with one-click generic substitution.
  - **Vernacular Voice Dosage Explainer (Telugu & English TTS)**: Text-to-speech audio reader that speaks out clear dosage instructions in local languages (Telugu - తెలుగు & English) for illiterate or elderly rural patients, accompanied by visual glyphs (🌅 Morning Sun, ☀️ Afternoon, 🌙 Bedtime Moon, 🍽️ Post-Meal).
  - **2G Keypad SMS Slip**: Generates concise GSM-7 compliant SMS slips (< 160 characters) tailored for basic non-smartphone keypad phones.
  - **Offline-First Synchronization**: Caches transactions locally in browser storage when rural cellular networks fail, syncing automatically when connectivity resumes.

---

## 🏗️ Technology Stack

| Layer | Technology | Details |
|---|---|---|
| **Backend** | Python 3.11 + FastAPI | Async REST API, route modularity, security headers |
| **Validation** | Pydantic v2 | Strict schema parsing, type safety, sanitization |
| **Database** | MySQL (with SQLite Fallback) | Relational schema with automatic zero-friction fallback |
| **ORM** | SQLAlchemy 2.0 | Declarative models, relationship mapping, connection pooling |
| **PDF & QR** | ReportLab + qrcode[pil] | In-memory cryptographic QR code & PDF receipt compilation |
| **Frontend** | HTML5, CSS3, Vanilla JS | Custom responsive UI, zero external CSS frameworks (no Tailwind) |

---

## 🗄️ Database Architecture & Setup

### Database Models
- `Doctor`: id, name, license_number, specialization, clinic_name, phone, email
- `Patient`: id, full_name, age, gender, phone (indexed), email, blood_group, address
- `HealthSlip`: slip_number, doctor_id, patient_id, visit_date, symptoms, diagnosis, subtotal, tax_amount, grand_total, verification_hash, status
- `ReceiptItem`: health_slip_id, item_type (CONSULTATION, MEDICATION, LAB_TEST), item_name, unit_price, quantity, total_price
- `MedicationReminder`: health_slip_id, patient_id, medicine_name, dosage, timing_slot, schedule_time, is_done, last_taken_at
- `OtpVerification`: phone_number, otp_hash, salt, attempts_count, expires_at, is_verified, access_token
- `AuditLog`: action, actor_type, identifier, status, ip_address, details

### Configuring MySQL
By default, the application is pre-configured to connect to MySQL (`localhost:3306`).
To connect to your local MySQL instance, edit `.env`:
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_actual_mysql_password
MYSQL_DB=healthslip_db
DATABASE_URL=mysql+pymysql://root:your_actual_mysql_password@localhost:3306/healthslip_db
```
*Note: If MySQL credentials are not yet configured, the system automatically runs on SQLite fallback (`sqlite:///./healthslip.db`) so you can test immediately with zero errors!*

---

## 🚀 How to Run Locally

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Start the Server
```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8005 --reload
```
Open **[http://127.0.0.1:8005](http://127.0.0.1:8005)** in your browser.

### 3. Run Automated Tests
```powershell
python -m pytest tests/test_healthslip.py -v
```

---

## 🐳 Production Deployment Guide

HealthSlip AI is containerized and cloud-ready for high-availability production environments.

### Option A: 1-Click Docker Compose (FastAPI + MySQL 8.0)
The complete production stack (multi-worker FastAPI, WebSockets hub, MySQL with persistent storage, automated schema migrations, and health checks) can be started with a single command:

```bash
# On Linux / macOS / Cloud VM:
./deploy.sh

# On Windows:
.\deploy.ps1

# Or standard Docker Compose:
docker compose up -d --build
```
Once started, the application will be live at **`http://localhost:8005`**.

### Option B: Cloud Platform Deployments

- **Render (`render.yaml`)**:
  Connect your GitHub repository to Render. Render will automatically detect `render.yaml` and deploy the Dockerized web service with zero manual configuration.
- **Railway (`railway.json`)**:
  Deploy with Railway CLI or GitHub integration:
  ```bash
  railway up
  ```
- **Fly.io (`fly.toml`)**:
  Launch globally distributed containers:
  ```bash
  fly launch
  fly deploy
  ```

### Option C: Enterprise Gunicorn Multi-Worker Execution
For bare-metal or cloud VMs running on multiple CPU cores:
```bash
gunicorn -c gunicorn_conf.py main:app
```
*Automatically scales workers based on available CPU cores with asynchronous Uvicorn ASGI workers.*

---

## 🧪 Interactive Testing Walkthrough

1. **Patient App View**:
   - See the mobile phone frame with "Good day, Minh" and the August 2022 calendar ribbon.
   - Click the amber **`DONE`** button on *Ibuprofen* or *Ibuprofen metisylat* to toggle doses and watch the adherence percentage update!
2. **Doctor AI Slip Builder**:
   - Click the **Doctor AI Slip Builder** tab in the top navigation.
   - Click one of the quick templates (e.g. *Sample: Migraine & Rhinitis*).
   - Click **`AI Parse & Populate Receipt`** — watch the AI extract line items, calculate taxes, formulate dosage timings, and display clinical warnings.
   - Click **`Issue Verified Health Slip`** to save to the database with a cryptographic HMAC-SHA256 seal.
3. **OTP Patient Verification**:
   - Click **`OTP Verification`** in the top navbar or bell icon on the mobile phone.
   - Enter patient phone number (`+1 555-019-2834`) and click **Send Verification Code**.
   - Click the Dev Sandbox OTP code in the yellow helper banner to auto-fill the 6 digits.
   - Click **Verify Identity & Access Slips** to unlock the secure patient vault.
4. **Download PDF Receipt**:
   - Click **Download Official PDF Receipt** to generate and download the printable document.
5. **Public QR Verifier**:
   - Navigate to **QR Verifier**, enter a slip number (e.g. `HSL-2022-82194`), and click **Verify Receipt** to view the cryptographic authenticity confirmation.
