// HealthSlip AI - Production Grade API Client with Real-Time Authentication

const API = {
  // Session Token Storage
  getSessionToken() {
    return localStorage.getItem('healthslip_session_token') || '';
  },

  setSessionToken(token) {
    if (token) {
      localStorage.setItem('healthslip_session_token', token);
    } else {
      localStorage.removeItem('healthslip_session_token');
    }
  },

  // Cached User Profile
  getCurrentUser() {
    const raw = localStorage.getItem('healthslip_user_profile');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  },

  setCurrentUser(user) {
    if (user) {
      localStorage.setItem('healthslip_user_profile', JSON.stringify(user));
    } else {
      localStorage.removeItem('healthslip_user_profile');
    }
  },

  // Legacy Patient Slip Access Token compatibility
  getPatientToken() {
    return localStorage.getItem('healthslip_patient_token') || this.getSessionToken() || '';
  },

  setPatientToken(token) {
    if (token) {
      localStorage.setItem('healthslip_patient_token', token);
    } else {
      localStorage.removeItem('healthslip_patient_token');
    }
  },

  clearSession() {
    this.setSessionToken(null);
    this.setCurrentUser(null);
    this.setPatientToken(null);
  },

  // Base HTTP Request wrapper
  async request(endpoint, options = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json'
    };

    const sessionToken = this.getSessionToken();
    if (sessionToken) {
      defaultHeaders['Authorization'] = `Bearer ${sessionToken}`;
      defaultHeaders['X-Session-Token'] = sessionToken;
    }

    const patientToken = this.getPatientToken();
    if (patientToken) {
      defaultHeaders['X-Patient-Token'] = patientToken;
    }

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...(options.headers || {})
      }
    };

    try {
      const response = await fetch(endpoint, config);
      const isJson = response.headers.get('content-type')?.includes('application/json');
      const data = isJson ? await response.json() : await response.text();

      if (!response.ok) {
        // If 401 Unauthorized and was previously logged in, trigger session expiration handling
        if (response.status === 401 && this.getSessionToken()) {
          console.warn("Session expired or invalid. Clearing client credentials.");
          window.dispatchEvent(new CustomEvent('healthslip:session-expired', { detail: data }));
        }

        const errorMsg = data?.detail || data?.message || 'Network request failed';
        const err = new Error(errorMsg);
        err.status = response.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  },

  post(endpoint, body) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  },

  // Auth Operations
  async login(emailOrPhone, password, rememberMe = false) {
    const res = await this.post('/api/auth/login', {
      email_or_phone: emailOrPhone,
      password: password,
      remember_me: rememberMe
    });

    if (res.access_token) {
      this.setSessionToken(res.access_token);
      if (res.user) {
        this.setCurrentUser(res.user);
      }
    }
    return res;
  },

  async loginWithOtp(phoneNumber, otpCode) {
    const res = await this.post('/api/auth/login-otp', {
      phone_number: phoneNumber,
      otp_code: otpCode
    });

    if (res.access_token) {
      this.setSessionToken(res.access_token);
      this.setPatientToken(res.access_token);
      if (res.user) {
        this.setCurrentUser(res.user);
      }
    }
    return res;
  },

  async register(payload) {
    const res = await this.post('/api/auth/register', payload);
    if (res.access_token) {
      this.setSessionToken(res.access_token);
      if (res.user) {
        this.setCurrentUser(res.user);
      }
    }
    return res;
  },

  async logout() {
    try {
      await this.post('/api/auth/logout', {});
    } catch (err) {
      console.warn("Server logout request finished with note:", err);
    } finally {
      this.clearSession();
    }
  },

  async checkAuthStatus() {
    try {
      const res = await this.get('/api/auth/status');
      if (res.authenticated && res.user) {
        this.setCurrentUser(res.user);
        return res;
      } else {
        this.clearSession();
        return { authenticated: false };
      }
    } catch (err) {
      return { authenticated: false, error: err.message };
    }
  },

  // Urban & Rural Medical Store (Pharmacy) APIs
  async getPharmacyInventory() {
    return this.get('/api/pharmacy/inventory');
  },

  async getPharmacyQueue(storeType = 'URBAN') {
    return this.get(`/api/pharmacy/queue?store_type=${encodeURIComponent(storeType)}`);
  },

  async dispensePrescription(payload) {
    return this.post('/api/pharmacy/dispense', payload);
  },

  async lookupGeneric(medicineName) {
    return this.post('/api/pharmacy/generic-lookup', { medicine_name: medicineName });
  },

  async getPrescriptionSavings(slipNumber) {
    return this.get(`/api/pharmacy/prescription-savings/${encodeURIComponent(slipNumber)}`);
  },

  async getRuralSmsSlip(slipNumber) {
    return this.post('/api/pharmacy/sms-slip', { slip_number: slipNumber });
  },

  async getAudioDosageScript(medicineName, language = 'hi') {
    return this.post('/api/pharmacy/audio-dosage', { medicine_name: medicineName, language });
  },

  async adjustStock(medicineId, quantityChange) {
    return this.post('/api/pharmacy/inventory/adjust', {
      medicine_id: medicineId,
      quantity_change: quantityChange
    });
  }
};
