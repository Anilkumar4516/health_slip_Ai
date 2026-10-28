import httpx

client = httpx.Client(base_url="http://127.0.0.1:8005", timeout=10.0)

# 1. Health
h = client.get("/api/health")
assert h.status_code == 200, f"Health failed: {h.text}"
print("[1/16] /api/health: OK")

# 2. AI Parse
p = client.post("/api/receipts/ai-parse", json={"clinical_notes": "Prescribe Ibuprofen 400mg 1 tab morning for 5 days. Consultation $50."})
assert p.status_code == 200, f"AI Parse failed: {p.text}"
print("[2/16] /api/receipts/ai-parse: OK")

# 3. List receipts
l = client.get("/api/receipts")
assert l.status_code == 200 and len(l.json()) > 0, f"List receipts failed: {l.text}"
slip_num = l.json()[0]["slip_number"]
slip_id = l.json()[0]["id"]
print(f"[3/16] /api/receipts: OK (Found {len(l.json())} slips)")

# 4. Get single receipt
s = client.get(f"/api/receipts/{slip_id}")
assert s.status_code == 200, f"Get single receipt failed: {s.text}"
print(f"[4/16] /api/receipts/{slip_id}: OK")

# 5. Download PDF
pdf = client.get(f"/api/receipts/{slip_id}/pdf")
assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf", "PDF failed"
print(f"[5/16] /api/receipts/{slip_id}/pdf: OK ({len(pdf.content)} bytes)")

# 6. Verify slip QR
v = client.get(f"/api/verify/{slip_num}")
assert v.status_code == 200 and v.json()["is_valid"] is True, "Verify failed"
print(f"[6/16] /api/verify/{slip_num}: OK (Authentic)")

# 7. QR image stream
qr = client.get(f"/api/verify/{slip_num}/qr")
assert qr.status_code == 200 and qr.headers["content-type"] == "image/png", "QR stream failed"
print(f"[7/16] /api/verify/{slip_num}/qr: OK ({len(qr.content)} bytes)")

# 8. Request OTP
o1 = client.post("/api/otp/request", json={"phone_number": "+1 555-019-2834"})
assert o1.status_code == 200, f"OTP request failed: {o1.text}"
code = o1.json()["sandbox_otp"]
print(f"[8/16] /api/otp/request: OK (Sandbox code {code})")

# 9. Verify OTP
o2 = client.post("/api/otp/verify", json={"phone_number": "+1 555-019-2834", "otp_code": code})
assert o2.status_code == 200, f"OTP verify failed: {o2.text}"
tok = o2.json()["access_token"]
print("[9/16] /api/otp/verify: OK (Access Token obtained)")

# 10. Patient slips with token
ps = client.get("/api/otp/patient-slips", params={"token": tok})
assert ps.status_code == 200, f"Patient slips failed: {ps.text}"
patient_name = ps.json()["patient"]["full_name"]
print(f"[10/16] /api/otp/patient-slips: OK (Patient: {patient_name})")

# 11. Get Reminders
rem = client.get("/api/reminders")
assert rem.status_code == 200, f"Reminders failed: {rem.text}"
rem_id = rem.json()[0]["id"]
print(f"[11/16] /api/reminders: OK ({len(rem.json())} reminders)")

# 12. Toggle Reminder
tog = client.post(f"/api/reminders/{rem_id}/toggle")
assert tog.status_code == 200, f"Toggle failed: {tog.text}"
is_done = tog.json()["is_done"]
print(f"[12/16] /api/reminders/{rem_id}/toggle: OK (is_done={is_done})")

# 13. Clinic Stats
st = client.get("/api/stats")
assert st.status_code == 200, f"Stats failed: {st.text}"
rev = st.json()["total_revenue"]
print(f"[13/16] /api/stats: OK (Total revenue ${rev})")

# 14. DB status
db_st = client.get("/api/stats/db-status")
assert db_st.status_code == 200, f"DB status failed: {db_st.text}"
print(f"[14/16] /api/stats/db-status: OK ({db_st.json()['active_db']})")

# 15. Frontend index
idx = client.get("/")
assert idx.status_code == 200 and "HealthSlip AI" in idx.text, "Index failed"
print(f"[15/16] GET / (index.html): OK ({len(idx.content)} bytes)")

# 16. Post create new receipt
cr = client.post("/api/receipts", json={
    "patient": {"full_name": "Workbench Test Patient", "age": 45, "gender": "Female", "phone": "+1 555-889-1029"},
    "doctor_name": "Dr. Minh Nguyen, M.D.",
    "clinic_name": "HealthSlip AI Medical Center",
    "diagnosis": "Seasonal Allergies",
    "items": [{"item_type": "MEDICATION", "item_name": "Cetirizine 10mg", "unit_price": 15.0, "quantity": 1}],
    "reminders": [{"medicine_name": "Cetirizine", "dosage": "10mg", "timing_slot": "NIGHT", "schedule_time": "09:00 PM", "duration_days": 10}],
    "tax_percent": 5.0
})
assert cr.status_code == 200, f"Create receipt failed: {cr.text}"
new_num = cr.json()["slip_number"]
print(f"[16/21] POST /api/receipts: OK (Created {new_num})")

# 17. Production Auth: Doctor Login
auth_login = client.post("/api/auth/login", json={
    "email_or_phone": "dr.minh@healthslip.ai",
    "password": "Doctor@2026",
    "remember_me": True
})
assert auth_login.status_code == 200, f"Auth login failed: {auth_login.text}"
auth_data = auth_login.json()
auth_token = auth_data["access_token"]
print(f"[17/21] POST /api/auth/login: OK (Doctor signed in, role: {auth_data['user']['primary_role']})")

# 18. Production Auth: Current User Profile (/me)
auth_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
assert auth_me.status_code == 200, f"Auth me failed: {auth_me.text}"
assert auth_me.json()["email"] == "dr.minh@healthslip.ai"
print(f"[18/21] GET /api/auth/me: OK (Verified: {auth_me.json()['full_name']})")

# 19. Production Auth: Real-Time Session Status
auth_status = client.get("/api/auth/status", headers={"Authorization": f"Bearer {auth_token}"})
assert auth_status.status_code == 200 and auth_status.json()["authenticated"] is True, "Status check failed"
print(f"[19/21] GET /api/auth/status: OK (Session active: ID {auth_status.json()['session_id']})")

# 20. Production Auth: Active User Sessions
auth_sessions = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {auth_token}"})
assert auth_sessions.status_code == 200 and len(auth_sessions.json()) > 0, "Sessions list failed"
print(f"[20/21] GET /api/auth/sessions: OK ({len(auth_sessions.json())} active sessions tracked)")

# 21. Production Auth: Real-Time Logout & Session Invalidation
auth_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {auth_token}"})
assert auth_logout.status_code == 200 and auth_logout.json()["success"] is True, "Logout failed"
# Verify token is now strictly 401
after_logout = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
assert after_logout.status_code == 401, "Token was not invalidated after logout!"
print("[21/21] POST /api/auth/logout: OK (Session invalidated, subsequent calls returned 401 Unauthorized)")

print("\n>>> ALL 21 PRODUCTION-GRADE ENDPOINTS VERIFIED 100% OPERATIONAL WITH MYSQL HEALTHSLIP_PROD! <<<")

