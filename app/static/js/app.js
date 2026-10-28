// HealthSlip AI - Main Orchestrator & View Switcher

document.addEventListener('DOMContentLoaded', () => {
  initClock();
  initCalendarRibbon();
  checkDatabaseStatus();
  refreshReminders();
  loadInitialSlip();

  // Populate initial items in doctor view
  fillSamplePrompt('migraine');

  // Real-time synchronization heartbeat (polls live metrics & DB status)
  setInterval(() => {
    checkDatabaseStatus();
    const analyticsActive = document.getElementById('analytics-view')?.classList.contains('active');
    if (analyticsActive) {
      loadAnalytics();
    }
  }, 3500);
});

function initClock() {
  const clockEl = document.getElementById('phone-clock');
  function update() {
    const d = new Date();
    let hours = d.getHours();
    const minutes = String(d.getMinutes()).padStart(2, '0');
    if (clockEl) {
      clockEl.textContent = `${hours}:${minutes}`;
    }
  }
  update();
  setInterval(update, 30000);
}

function switchView(viewId) {
  // Update view panels
  document.querySelectorAll('.view-panel').forEach(panel => {
    panel.classList.remove('active');
  });
  const target = document.getElementById(viewId);
  if (target) target.classList.add('active');

  // Update navbar tab buttons
  document.querySelectorAll('.nav-tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });

  if (viewId === 'patient-view') document.getElementById('tab-patient-btn')?.classList.add('active');
  if (viewId === 'doctor-view') document.getElementById('tab-doctor-btn')?.classList.add('active');
  if (viewId === 'verify-view') document.getElementById('tab-verify-btn')?.classList.add('active');
  if (viewId === 'analytics-view') {
    document.getElementById('tab-analytics-btn')?.classList.add('active');
    loadAnalytics();
  }
}

async function checkDatabaseStatus() {
  try {
    const res = await API.get('/api/health');
    const badgeText = document.getElementById('db-name-text');
    const dot = document.getElementById('db-dot');
    
    if (res.database) {
      const dbType = res.database.active_db;
      const dbName = res.database.configured_mysql_db || 'healthslip_prod';
      if (badgeText) badgeText.textContent = `${dbType}: ${dbName} (Live)`;
      if (dot) {
        dot.style.background = 'var(--emerald)';
        dot.style.boxShadow = '0 0 8px rgba(16, 185, 129, 0.7)';
      }
    }
  } catch (err) {
    console.error("Health check error:", err);
  }
}

async function loadInitialSlip() {
  try {
    const slips = await API.get('/api/receipts?limit=1');
    if (slips && slips.length > 0) {
      const fullSlip = await API.get(`/api/receipts/${slips[0].id}`);
      renderActiveSlipPreview(fullSlip);
    }
  } catch (err) {
    console.error("Failed to load initial slip:", err);
  }
}

// Scanner Simulator Modal
function openScannerModal() {
  const modal = document.getElementById('scanner-modal');
  if (modal) modal.classList.add('active');
}

function closeScannerModal() {
  const modal = document.getElementById('scanner-modal');
  if (modal) modal.classList.remove('active');
}

function simulateScanDetected() {
  closeScannerModal();
  switchView('verify-view');
  const input = document.getElementById('verify-slip-input');
  if (input) {
    input.value = activePatientSlip ? activePatientSlip.slip_number : 'HSL-2022-82194';
    runPublicVerification();
  }
}

// Public QR Code Verification Logic
async function runPublicVerification() {
  const slipInput = document.getElementById('verify-slip-input')?.value;
  if (!slipInput || slipInput.trim().length < 4) {
    alert("Please enter a valid Receipt Slip Number e.g. HSL-2022-82194");
    return;
  }

  const resultCard = document.getElementById('verify-result-card');
  if (!resultCard) return;

  resultCard.style.display = 'block';
  resultCard.innerHTML = `<div style="text-align: center; color: var(--text-muted);">Verifying cryptographic seal...</div>`;

  try {
    const cleanNum = slipInput.trim().toUpperCase();
    const data = await API.get(`/api/verify/${cleanNum}`);

    if (data.is_valid) {
      resultCard.style.borderColor = 'var(--emerald)';
      resultCard.style.background = '#f0fdf4';
      resultCard.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
          <div style="width: 32px; height: 32px; border-radius: 50%; background: #10b981; color: white; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <div>
            <div style="font-weight: 800; font-size: 1rem; color: #047857;">OFFICIAL MEDICAL RECEIPT VERIFIED</div>
            <div style="font-size: 0.75rem; color: #065f46;">HMAC-SHA256 Integrity Seal Confirmed Authenticated</div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.85rem; margin-bottom: 0.75rem;">
          <div><b>Receipt Number:</b> ${data.slip_number}</div>
          <div><b>Issuing Hospital:</b> ${data.clinic_name}</div>
          <div><b>Physician:</b> ${data.doctor_name}</div>
          <div><b>Patient (Protected):</b> ${data.patient_masked_name}</div>
          <div><b>Issued Date:</b> ${new Date(data.issued_date).toLocaleDateString()}</div>
          <div><b>Total Amount:</b> $${data.grand_total.toFixed(2)} (${data.payment_status})</div>
        </div>

        <div style="font-size: 0.72rem; color: #065f46; font-family: monospace; word-break: break-all; background: white; padding: 6px; border-radius: 4px; border: 1px solid #a7f3d0;">
          Verification Hash: ${data.verification_hash}
        </div>
      `;
    } else {
      resultCard.style.borderColor = 'var(--rose)';
      resultCard.style.background = '#fef2f2';
      resultCard.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
          <div style="width: 32px; height: 32px; border-radius: 50%; background: #ef4444; color: white; display: flex; align-items: center; justify-content: center;">✕</div>
          <div style="font-weight: 800; font-size: 1rem; color: #b91c1c;">VERIFICATION FAILED / UNKNOWN SLIP</div>
        </div>
        <p style="font-size: 0.85rem; color: #991b1b;">${data.message}</p>
      `;
    }
  } catch (err) {
    resultCard.innerHTML = `<div style="color: var(--rose);">Verification error: ${err.message}</div>`;
  }
}

// Analytics Loader
async function loadAnalytics() {
  try {
    const stats = await API.get('/api/stats');
    
    document.getElementById('metric-slips').textContent = stats.total_slips || 0;
    document.getElementById('metric-revenue').textContent = `$${(stats.total_revenue || 0).toFixed(2)}`;
    document.getElementById('metric-otp-rate').textContent = `${stats.otp_success_rate || 100}%`;
    document.getElementById('metric-adherence').textContent = `${stats.adherence_rate || 0}%`;

    if (stats.db_status) {
      document.getElementById('metric-db-title').textContent = `Database Engine: ${stats.db_status.active_db}`;
      document.getElementById('metric-db-detail').textContent = stats.db_status.detail;
    }

    const auditTbody = document.getElementById('audit-trail-tbody');
    if (auditTbody && stats.recent_audits) {
      auditTbody.innerHTML = stats.recent_audits.map(a => `
        <tr>
          <td><span style="font-family: monospace; font-size: 0.75rem;">${a.created_at}</span></td>
          <td><b>${a.action}</b></td>
          <td><span class="pill-dosage-tag" style="background: #eff6ff; color: #1d4ed8;">${a.actor_type}</span></td>
          <td>${a.identifier || '-'}</td>
          <td><span style="font-weight: 700; color: ${a.status === 'SUCCESS' ? 'var(--emerald-text)' : 'var(--rose)'};">${a.status}</span></td>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${a.details || ''}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error("Failed to load analytics:", err);
  }
}
