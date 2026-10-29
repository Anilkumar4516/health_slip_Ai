// HealthSlip AI - Real-Time Production-Grade Authentication Engine

let authEventSource = null;

document.addEventListener('DOMContentLoaded', () => {
  initAuth();
});

async function initAuth() {
  // 1. Check existing session status on initial load
  const sessionToken = API.getSessionToken();
  if (sessionToken) {
    try {
      const res = await API.checkAuthStatus();
      if (res.authenticated && res.user) {
        renderAuthHeader(res.user);
        applyUserRolePreferences(res.user);
      } else {
        renderAuthHeader(null);
      }
    } catch {
      renderAuthHeader(null);
    }
  } else {
    renderAuthHeader(null);
  }

  // 2. Real-time Cross-Tab Synchronization via storage event
  window.addEventListener('storage', (e) => {
    if (e.key === 'healthslip_session_token' || e.key === 'healthslip_user_profile') {
      const updatedUser = API.getCurrentUser();
      renderAuthHeader(updatedUser);
      if (updatedUser) {
        applyUserRolePreferences(updatedUser);
        showToast(`Session synchronized: Signed in as ${updatedUser.full_name}`, 'info');
      } else {
        showToast('Session ended in another window. Logged out.', 'warning');
      }
    }
  });

  // 3. Listen for session expiration events from API client
  window.addEventListener('healthslip:session-expired', () => {
    API.clearSession();
    renderAuthHeader(null);
    showToast('Your session has expired. Please sign in again.', 'warning');
  });

  // 4. Initialize Real-Time SSE Stream for multi-client live events
  connectAuthStream();

  // 5. Close popovers on outside click
  document.addEventListener('click', (e) => {
    const popover = document.getElementById('user-profile-popover');
    const trigger = document.getElementById('user-profile-badge');
    if (popover && popover.classList.contains('active')) {
      if (!popover.contains(e.target) && !trigger?.contains(e.target)) {
        popover.classList.remove('active');
      }
    }
  });
}

// Connect to Server-Sent Events (SSE) stream for real-time auth notifications
function connectAuthStream() {
  if (window.EventSource && !authEventSource) {
    try {
      authEventSource = new EventSource('/api/auth/stream');

      authEventSource.addEventListener('USER_LOGIN', (e) => {
        try {
          const payload = JSON.parse(e.data);
          // If Analytics tab is open, refresh audits immediately
          if (document.getElementById('analytics-view')?.classList.contains('active')) {
            loadAnalytics();
          }
        } catch (err) {
          console.debug("SSE USER_LOGIN parse note:", err);
        }
      });

      authEventSource.addEventListener('USER_LOGOUT', (e) => {
        try {
          const payload = JSON.parse(e.data);
          // If current user was logged out by server, sync client
          const currentUser = API.getCurrentUser();
          if (currentUser && payload.data?.user?.user_id === currentUser.id) {
            API.clearSession();
            renderAuthHeader(null);
            showToast('Your session was revoked. Logged out.', 'warning');
          }
          if (document.getElementById('analytics-view')?.classList.contains('active')) {
            loadAnalytics();
          }
        } catch (err) {
          console.debug("SSE USER_LOGOUT parse note:", err);
        }
      });

      authEventSource.onerror = () => {
        // Silent reconnect attempt by EventSource
      };
    } catch (err) {
      console.warn("Real-time SSE stream unavailable:", err);
    }
  }
}

// Update Top Navigation Bar with Authenticated or Unauthenticated State
function renderAuthHeader(user) {
  const container = document.getElementById('header-auth-container');
  if (!container) return;

  if (user) {
    const initials = user.full_name ? user.full_name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : 'U';
    const roleCode = user.primary_role || 'PATIENT';
    
    // Choose role badge styling
    let roleBadgeClass = 'badge-role-patient';
    if (roleCode === 'DOCTOR') roleBadgeClass = 'badge-role-doctor';
    if (roleCode === 'ADMIN') roleBadgeClass = 'badge-role-admin';

    container.innerHTML = `
      <div class="user-pill-wrapper">
        <button class="user-profile-badge" id="user-profile-badge" onclick="toggleUserProfilePopover(event)">
          <span class="user-live-indicator" title="Real-Time Active Session"></span>
          <span class="user-avatar-initials">${initials}</span>
          <div class="user-pill-info">
            <span class="user-pill-name">${user.full_name}</span>
            <span class="user-pill-role ${roleBadgeClass}">${roleCode}</span>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
        </button>

        <!-- Dropdown Popover Menu -->
        <div class="user-profile-popover" id="user-profile-popover">
          <div class="popover-header">
            <div class="popover-avatar">${initials}</div>
            <div style="overflow: hidden;">
              <div class="popover-user-name">${user.full_name}</div>
              <div class="popover-user-email">${user.email}</div>
              <div class="popover-role-tag ${roleBadgeClass}">${roleCode} • Verified</div>
            </div>
          </div>

          <div class="popover-body">
            <div class="popover-info-row">
              <span class="popover-label">Phone</span>
              <span class="popover-value">${user.phone_number}</span>
            </div>
            ${user.practitioner_license ? `
              <div class="popover-info-row">
                <span class="popover-label">Medical License</span>
                <span class="popover-value">${user.practitioner_license}</span>
              </div>
              <div class="popover-info-row">
                <span class="popover-label">Specialization</span>
                <span class="popover-value">${user.practitioner_specialization || 'Clinical'}</span>
              </div>
            ` : ''}
            <div class="popover-info-row">
              <span class="popover-label">Session Status</span>
              <span class="popover-value" style="color: var(--emerald-text); font-weight: 700;">● Active (Live)</span>
            </div>
          </div>

          <div class="popover-footer">
            <button class="btn-popover-logout" onclick="handleRealtimeLogout()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              Sign Out Securely
            </button>
          </div>
        </div>
      </div>
    `;
  } else {
    // Unauthenticated State
    container.innerHTML = `
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <button class="btn-auth-signin" id="btn-auth-signin" onclick="openAuthModal('signin')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          Sign In
        </button>
        <button class="btn-auth-demo" onclick="openAuthModal('signin', true)" title="Quick 1-Click Demo Login">
          Demo
        </button>
      </div>
    `;
  }
}

function toggleUserProfilePopover(e) {
  e.stopPropagation();
  const popover = document.getElementById('user-profile-popover');
  if (popover) {
    popover.classList.toggle('active');
  }
}

// Role-based tailoring
function applyUserRolePreferences(user) {
  if (user.primary_role === 'DOCTOR') {
    // If doctor, auto-populate Doctor AI slip builder with doctor's verified credentials
    const docNameInput = document.getElementById('doc-name-input');
    const docLicenseInput = document.getElementById('doc-license-input');
    if (docNameInput) docNameInput.value = user.full_name;
    if (docLicenseInput && user.practitioner_license) docLicenseInput.value = user.practitioner_license;
  } else if (user.primary_role === 'PATIENT') {
    // If patient, personalize patient app greeting and avatar
    const nameEl = document.getElementById('patient-display-name');
    const avatarEl = document.getElementById('patient-avatar-letter');
    if (nameEl) nameEl.textContent = user.full_name;
    if (avatarEl) avatarEl.textContent = user.full_name.charAt(0).toUpperCase();

    // Unlock patient slips
    loadPatientVerifiedSlips();
  }
}

// Modal open/close & tabs
function openAuthModal(defaultTab = 'signin', autoSelectDoctor = false) {
  const modal = document.getElementById('auth-modal');
  if (modal) {
    modal.classList.add('active');
    switchAuthTab(defaultTab);
    resetAuthForms();
    if (autoSelectDoctor) {
      fillDemoCredentials('doctor');
    }
  }
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
  if (modal) {
    modal.classList.remove('active');
  }
}

function switchAuthTab(tabName) {
  document.querySelectorAll('.auth-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.auth-tab-content').forEach(c => c.classList.remove('active'));

  const tabBtn = document.getElementById(`tab-auth-${tabName}-btn`);
  const content = document.getElementById(`auth-content-${tabName}`);
  if (tabBtn) tabBtn.classList.add('active');
  if (content) content.classList.add('active');

  const feedback = document.getElementById('auth-feedback-msg');
  if (feedback) feedback.textContent = '';
}

function resetAuthForms() {
  const feedback = document.getElementById('auth-feedback-msg');
  if (feedback) {
    feedback.textContent = '';
    feedback.className = 'auth-feedback-box';
  }
}

// Quick 1-Click Demo Fillers
function fillDemoCredentials(role) {
  switchAuthTab('signin');
  const idInput = document.getElementById('signin-identity');
  const passInput = document.getElementById('signin-password');

  if (role === 'doctor') {
    if (idInput) idInput.value = 'dr.rao@healthslip.ai';
    if (passInput) passInput.value = 'Doctor@2026';
    highlightInputPulse(idInput);
  } else if (role === 'patient') {
    if (idInput) idInput.value = 'rajesh.kumar@example.com';
    if (passInput) passInput.value = 'Patient@2026';
    highlightInputPulse(idInput);
  } else if (role === 'admin') {
    if (idInput) idInput.value = 'admin@healthslip.ai';
    if (passInput) passInput.value = 'Admin@2026';
    highlightInputPulse(idInput);
  }
}

function highlightInputPulse(el) {
  if (!el) return;
  el.style.transition = 'all 0.3s ease';
  el.style.borderColor = 'var(--primary)';
  el.style.boxShadow = '0 0 12px rgba(37, 99, 235, 0.4)';
  setTimeout(() => {
    el.style.borderColor = '';
    el.style.boxShadow = '';
  }, 1000);
}

// Toggle password visibility
function togglePasswordVisibility(inputId, btnEl) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    btnEl.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
    `;
  } else {
    input.type = 'password';
    btnEl.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
    `;
  }
}

// Submit Sign In (Credentials)
async function submitLogin(e) {
  if (e) e.preventDefault();
  const identity = document.getElementById('signin-identity')?.value?.trim();
  const password = document.getElementById('signin-password')?.value;
  const remember = document.getElementById('signin-remember')?.checked || false;
  const btn = document.getElementById('btn-submit-signin');
  const feedback = document.getElementById('auth-feedback-msg');

  if (!identity || !password) {
    showAuthError("Please provide your email/phone and password.");
    return;
  }

  setButtonLoading(btn, true, "Signing in...");
  if (feedback) feedback.textContent = '';

  try {
    const res = await API.login(identity, password, remember);
    setButtonLoading(btn, false, "Sign In");

    showAuthSuccess(`Welcome, ${res.user.full_name}! Session verified.`);
    renderAuthHeader(res.user);
    applyUserRolePreferences(res.user);
    showToast(`Authenticated as ${res.user.full_name} (${res.user.primary_role})`, 'success');

    setTimeout(() => {
      closeAuthModal();
    }, 800);

  } catch (err) {
    setButtonLoading(btn, false, "Sign In");
    showAuthError(err.message || "Invalid credentials. Please verify your details.");
  }
}

// Submit Phone + OTP Login
async function submitOtpLogin(e) {
  if (e) e.preventDefault();
  const phone = document.getElementById('otp-login-phone')?.value?.trim();
  const code = document.getElementById('otp-login-code')?.value?.trim();
  const btn = document.getElementById('btn-submit-otp-login');

  if (!phone || !code || code.length < 4) {
    showAuthError("Please enter your mobile number and the 6-digit OTP code.");
    return;
  }

  setButtonLoading(btn, true, "Verifying OTP...");

  try {
    const res = await API.loginWithOtp(phone, code);
    setButtonLoading(btn, false, "Verify & Sign In");

    showAuthSuccess(`Authenticated via mobile! Welcome, ${res.user.full_name}.`);
    renderAuthHeader(res.user);
    applyUserRolePreferences(res.user);
    showToast(`OTP verified successfully for ${phone}`, 'success');

    setTimeout(() => {
      closeAuthModal();
    }, 800);

  } catch (err) {
    setButtonLoading(btn, false, "Verify & Sign In");
    showAuthError(err.message || "OTP verification failed. Please try again.");
  }
}

// Request OTP for the OTP Login tab
async function requestOtpForLoginTab() {
  const phone = document.getElementById('otp-login-phone')?.value?.trim();
  if (!phone || phone.length < 6) {
    showAuthError("Please enter a valid mobile number first.");
    return;
  }

  try {
    const res = await API.post('/api/otp/request', { phone_number: phone });
    showAuthSuccess(res.message);

    // If sandbox mode returned the code, offer quick fill
    if (res.sandbox_otp) {
      const codeInput = document.getElementById('otp-login-code');
      if (codeInput) codeInput.value = res.sandbox_otp;
      showToast(`Dev Sandbox OTP auto-filled: ${res.sandbox_otp}`, 'info');
    }
  } catch (err) {
    showAuthError(err.message || "Failed to send OTP.");
  }
}

// Submit Registration
async function submitRegister(e) {
  if (e) e.preventDefault();
  const fullName = document.getElementById('reg-fullname')?.value?.trim();
  const email = document.getElementById('reg-email')?.value?.trim();
  const phone = document.getElementById('reg-phone')?.value?.trim();
  const password = document.getElementById('reg-password')?.value;
  const roleCode = document.getElementById('reg-role')?.value || 'PATIENT';
  const license = document.getElementById('reg-license')?.value?.trim();
  const btn = document.getElementById('btn-submit-reg');

  if (!fullName || !email || !phone || !password) {
    showAuthError("Please fill out all required fields.");
    return;
  }

  if (password.length < 6) {
    showAuthError("Password must be at least 6 characters long.");
    return;
  }

  setButtonLoading(btn, true, "Creating Account...");

  try {
    const res = await API.register({
      full_name: fullName,
      email: email,
      phone_number: phone,
      password: password,
      role_code: roleCode,
      doctor_license: license || undefined
    });

    setButtonLoading(btn, false, "Create Account & Sign In");
    showAuthSuccess(`Account created! Welcome, ${res.user.full_name}.`);
    renderAuthHeader(res.user);
    applyUserRolePreferences(res.user);
    showToast(`Account registered: Signed in as ${res.user.full_name}`, 'success');

    setTimeout(() => {
      closeAuthModal();
    }, 900);

  } catch (err) {
    setButtonLoading(btn, false, "Create Account & Sign In");
    showAuthError(err.message || "Registration failed. Please check inputs.");
  }
}

// Real-Time Production Logout
async function handleRealtimeLogout() {
  const popover = document.getElementById('user-profile-popover');
  if (popover) popover.classList.remove('active');

  const prevUser = API.getCurrentUser();
  const userName = prevUser ? prevUser.full_name : 'User';

  try {
    await API.logout();
  } catch (err) {
    console.warn("Logout note:", err);
  } finally {
    // Immediate local UI transition
    renderAuthHeader(null);

    // Reset doctor inputs if they were filled from previous doctor account
    const docName = document.getElementById('doc-name-input');
    if (docName) docName.value = 'Dr. K. S. Rao, M.B.B.S., M.D.';

    showToast(`Logged out safely. Goodbye, ${userName}!`, 'info');

    // Trigger analytics refresh if open
    if (document.getElementById('analytics-view')?.classList.contains('active')) {
      loadAnalytics();
    }
  }
}

// Helpers
function showAuthError(msg) {
  const feedback = document.getElementById('auth-feedback-msg');
  if (feedback) {
    feedback.textContent = `✕ ${msg}`;
    feedback.className = 'auth-feedback-box error';
  }
}

function showAuthSuccess(msg) {
  const feedback = document.getElementById('auth-feedback-msg');
  if (feedback) {
    feedback.textContent = `✓ ${msg}`;
    feedback.className = 'auth-feedback-box success';
  }
}

function setButtonLoading(btn, isLoading, text) {
  if (!btn) return;
  btn.disabled = isLoading;
  btn.innerHTML = isLoading 
    ? `<span class="spinner-inline"></span> ${text}`
    : text;
}

// Password strength evaluator for registration
function evaluatePasswordStrength(val) {
  const bar = document.getElementById('reg-password-strength-bar');
  const label = document.getElementById('reg-password-strength-label');
  if (!bar || !label) return;

  if (!val) {
    bar.style.width = '0%';
    label.textContent = '';
    return;
  }

  let score = 0;
  if (val.length >= 6) score += 25;
  if (val.length >= 10) score += 25;
  if (/[0-9]/.test(val)) score += 25;
  if (/[^A-Za-z0-9]/.test(val)) score += 25;

  bar.style.width = `${score}%`;
  if (score <= 25) {
    bar.style.background = 'var(--rose)';
    label.textContent = 'Weak';
    label.style.color = 'var(--rose)';
  } else if (score <= 75) {
    bar.style.background = 'var(--amber)';
    label.textContent = 'Medium';
    label.style.color = 'var(--amber-dark)';
  } else {
    bar.style.background = 'var(--emerald)';
    label.textContent = 'Strong & Secure';
    label.style.color = 'var(--emerald-text)';
  }
}

// Toast notification system
function showToast(message, type = 'info') {
  let toastContainer = document.getElementById('app-toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'app-toast-container';
    toastContainer.className = 'app-toast-container';
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement('div');
  toast.className = `app-toast toast-${type}`;
  
  let icon = `ℹ️`;
  if (type === 'success') icon = `✓`;
  if (type === 'warning') icon = `⚠️`;
  if (type === 'error') icon = `✕`;

  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-message">${message}</span>
  `;

  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 4000);
}
