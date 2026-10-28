// HealthSlip AI - Patient Portal & OTP Verification Workflow

let otpTimerInterval = null;
let currentSandboxOtp = null;
let activePatientSlip = null;

function openOtpModal() {
  const modal = document.getElementById('otp-modal');
  if (modal) modal.classList.add('active');
  resetOtpForm();
}

function closeOtpModal() {
  const modal = document.getElementById('otp-modal');
  if (modal) modal.classList.remove('active');
  clearInterval(otpTimerInterval);
}

function resetOtpForm() {
  document.getElementById('otp-step-phone').style.display = 'block';
  document.getElementById('otp-step-code').style.display = 'none';
  document.getElementById('otp-feedback-msg').textContent = '';
  document.getElementById('otp-feedback-msg').style.color = 'inherit';
  clearOtpDigits();
}

function clearOtpDigits() {
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById(`otp-d${i}`);
    if (el) el.value = '';
  }
}

async function requestOtpCode() {
  const phone = document.getElementById('otp-input-phone')?.value;
  if (!phone || phone.trim().length < 6) {
    alert("Please enter a valid phone number.");
    return;
  }

  const feedback = document.getElementById('otp-feedback-msg');
  if (feedback) feedback.textContent = "Sending secure OTP...";

  try {
    const res = await API.post('/api/otp/request', {
      phone_number: phone
    });

    if (feedback) {
      feedback.textContent = res.message;
      feedback.style.color = "var(--emerald-text)";
    }

    // Switch to Code Step
    document.getElementById('otp-step-phone').style.display = 'none';
    document.getElementById('otp-step-code').style.display = 'block';

    // Dev Sandbox Mode Helper
    const sandboxToast = document.getElementById('dev-sandbox-toast');
    const sandboxCode = document.getElementById('dev-sandbox-code');
    if (res.sandbox_otp) {
      currentSandboxOtp = res.sandbox_otp;
      if (sandboxCode) sandboxCode.textContent = res.sandbox_otp;
      if (sandboxToast) sandboxToast.style.display = 'flex';
    } else {
      if (sandboxToast) sandboxToast.style.display = 'none';
    }

    // Start 5-minute Countdown
    startOtpCountdown(res.expires_in_seconds || 300);

    // Focus first digit
    document.getElementById('otp-d1')?.focus();

  } catch (err) {
    if (feedback) {
      feedback.textContent = err.message;
      feedback.style.color = "var(--rose)";
    }
  }
}

function autoFillSandboxOtp() {
  if (!currentSandboxOtp || currentSandboxOtp.length !== 6) return;
  for (let i = 0; i < 6; i++) {
    const el = document.getElementById(`otp-d${i + 1}`);
    if (el) el.value = currentSandboxOtp[i];
  }
  document.getElementById('otp-d6')?.focus();
}

function handleOtpInput(currentInput, nextId) {
  if (currentInput.value.length >= 1) {
    currentInput.value = currentInput.value.slice(-1); // Keep single digit
    if (nextId) {
      document.getElementById(nextId)?.focus();
    }
  }
}

function startOtpCountdown(seconds) {
  clearInterval(otpTimerInterval);
  let remaining = seconds;
  const timerVal = document.getElementById('otp-timer-val');

  function update() {
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    if (timerVal) {
      timerVal.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    if (remaining <= 0) {
      clearInterval(otpTimerInterval);
      if (timerVal) timerVal.textContent = "EXPIRED";
    }
    remaining--;
  }

  update();
  otpTimerInterval = setInterval(update, 1000);
}

async function submitVerifyOtp() {
  const phone = document.getElementById('otp-input-phone')?.value;
  let code = '';
  for (let i = 1; i <= 6; i++) {
    code += document.getElementById(`otp-d${i}`)?.value || '';
  }

  if (code.length !== 6) {
    alert("Please enter all 6 digits of the OTP code.");
    return;
  }

  const feedback = document.getElementById('otp-feedback-msg');
  if (feedback) feedback.textContent = "Verifying cryptographic token...";

  try {
    const res = await API.post('/api/otp/verify', {
      phone_number: phone,
      otp_code: code
    });

    if (res.access_token) {
      API.setPatientToken(res.access_token);
      updateAuthIndicator(true);
    }

    if (feedback) {
      feedback.textContent = "✅ Verification successful!";
      feedback.style.color = "var(--emerald-text)";
    }

    setTimeout(() => {
      closeOtpModal();
      loadPatientVerifiedSlips();
    }, 1000);

  } catch (err) {
    if (feedback) {
      feedback.textContent = err.message;
      feedback.style.color = "var(--rose)";
    }
  }
}

function updateAuthIndicator(isAuth) {
  const dot = document.getElementById('auth-status-dot');
  if (dot) {
    dot.style.background = isAuth ? 'var(--emerald)' : 'var(--amber)';
    dot.title = isAuth ? 'Patient Verified via OTP' : 'Verification Required';
  }
}

async function loadPatientVerifiedSlips() {
  try {
    const data = await API.get('/api/otp/patient-slips');
    if (data.slips && data.slips.length > 0) {
      renderActiveSlipPreview(data.slips[0]);
    }
    if (data.reminders) {
      cachedReminders = data.reminders;
      renderReminders(cachedReminders);
    }
    if (data.patient) {
      document.getElementById('patient-display-name').textContent = data.patient.full_name;
      document.getElementById('patient-avatar-letter').textContent = data.patient.full_name.charAt(0);
    }
  } catch (err) {
    console.warn("Patient slips not yet unlocked:", err);
  }
}

function renderActiveSlipPreview(slip) {
  activePatientSlip = slip;
  const container = document.getElementById('active-slip-preview-container');
  if (!container) return;

  const dateFmt = new Date(slip.visit_date || slip.created_at).toLocaleDateString('en-US', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });

  const qrSrc = `/api/verify/${slip.slip_number}/qr`;

  container.innerHTML = `
    <div class="receipt-paper">
      <div class="receipt-header-row">
        <div>
          <div style="font-size: 1rem; font-weight: 800; color: var(--navy);">${slip.clinic_name || 'HealthSlip AI Medical Center'}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">${slip.doctor_name || 'Dr. Minh Nguyen, M.D.'}</div>
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 4px;">Receipt: <b>${slip.slip_number}</b> • ${dateFmt}</div>
        </div>
        <div class="receipt-qr-wrap" title="Scan to verify tamper-proof seal">
          <img src="${qrSrc}" alt="Receipt QR">
        </div>
      </div>

      <!-- Diagnosis & Patient Demographics -->
      <div style="background: var(--surface-alt); padding: 0.75rem; border-radius: var(--radius-sm); font-size: 0.82rem;">
        <div><b>Patient:</b> ${slip.patient_name || slip.patient?.full_name || 'Minh'} (${slip.patient_phone || '+1 555-019-2834'})</div>
        <div style="margin-top: 2px;"><b>Diagnosis:</b> ${slip.diagnosis || 'Clinical Consultation'}</div>
        <div style="color: var(--text-muted); margin-top: 2px;"><b>Notes:</b> ${slip.symptoms || 'General routine care'}</div>
      </div>

      <!-- Itemized Preview Table -->
      <table style="width: 100%; font-size: 0.8rem; border-collapse: collapse;">
        <thead>
          <tr style="border-bottom: 1px solid var(--border); color: var(--text-muted);">
            <th style="text-align: left; padding: 4px 0;">Item Description</th>
            <th style="text-align: center; padding: 4px 0;">Type</th>
            <th style="text-align: right; padding: 4px 0;">Total</th>
          </tr>
        </thead>
        <tbody>
          ${(slip.items || []).map(it => `
            <tr style="border-bottom: 1px solid #f1f5f9;">
              <td style="padding: 5px 0;"><b>${it.item_name}</b></td>
              <td style="text-align: center; color: var(--text-muted);">${it.item_type}</td>
              <td style="text-align: right; font-weight: 600;">$${(it.total_price || (it.unit_price * it.quantity)).toFixed(2)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>

      <!-- Totals & Cryptographic Seal -->
      <div style="display: flex; justify-content: space-between; align-items: flex-end; padding-top: 0.5rem; border-top: 1.5px solid var(--border);">
        <div style="font-size: 0.7rem; color: var(--text-dim); max-width: 60%;">
          <b>HMAC-SHA256 Cryptographic Seal:</b><br/>
          <span style="font-family: monospace;">${(slip.verification_hash || '7f9a8b1c2d3e4f5a').substring(0, 24)}...</span>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 0.75rem; color: var(--text-muted);">${slip.payment_status} (${slip.payment_method || 'UPI/Card'})</div>
          <div style="font-size: 1.15rem; font-weight: 800; color: var(--primary);">$${(slip.grand_total || 0).toFixed(2)}</div>
        </div>
      </div>
    </div>
  `;
}

function downloadActivePdf() {
  if (!activePatientSlip) {
    alert("No active slip selected to download.");
    return;
  }
  const slipId = activePatientSlip.id;
  window.open(`/api/receipts/${slipId}/pdf`, '_blank');
}

function openPatientSlipsDrawer() {
  openOtpModal();
}
