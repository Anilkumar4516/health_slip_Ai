// HealthSlip AI - Urban & Rural Medical Store (Pharmacy) Controller with Real-Time WebSockets

let currentStoreMode = 'URBAN'; // 'URBAN' or 'RURAL'
let realtimeSocket = null;
let realtimeReconnectTimer = null;
let unreadPrescriptionsCount = 0;
let cachedQueue = [];
let cachedInventory = [];

document.addEventListener('DOMContentLoaded', () => {
  initRealtimeWebSocket();
  initNetworkListeners();
  loadPharmacyData();
});

// ==============================================================
// 1. REAL-TIME WEBSOCKET SYNCHRONIZATION
// ==============================================================

function initRealtimeWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;

  try {
    realtimeSocket = new WebSocket(wsUrl);

    realtimeSocket.onopen = () => {
      console.log('[WebSocket] Connected to HealthSlip AI Real-Time Channel');
      updateRealtimeBadge(true);
      // Flush any queued offline dispenses
      syncOfflineQueue();
    };

    realtimeSocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        handleRealtimeEvent(message);
      } catch (err) {
        console.warn('[WebSocket] Error parsing event:', err);
      }
    };

    realtimeSocket.onclose = () => {
      console.warn('[WebSocket] Disconnected from server. Retrying in 3s...');
      updateRealtimeBadge(false);
      scheduleReconnect();
    };

    realtimeSocket.onerror = (err) => {
      console.warn('[WebSocket] Socket error:', err);
      updateRealtimeBadge(false);
    };
  } catch (e) {
    console.warn('[WebSocket] Init failed:', e);
    updateRealtimeBadge(false);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (realtimeReconnectTimer) clearTimeout(realtimeReconnectTimer);
  realtimeReconnectTimer = setTimeout(() => {
    initRealtimeWebSocket();
  }, 3000);
}

function updateRealtimeBadge(isConnected) {
  const badgeEl = document.getElementById('pharmacy-realtime-badge');
  const dotEl = document.getElementById('pharmacy-realtime-dot');
  const textEl = document.getElementById('pharmacy-realtime-text');

  if (badgeEl && dotEl && textEl) {
    if (isConnected) {
      badgeEl.className = 'realtime-status-pill online';
      dotEl.className = 'status-pulse-dot green';
      textEl.textContent = 'Live Sync: Active';
    } else {
      badgeEl.className = 'realtime-status-pill offline';
      dotEl.className = 'status-pulse-dot red';
      textEl.textContent = navigator.onLine ? 'Connecting...' : 'Offline (Local Queue)';
    }
  }
}

function handleRealtimeEvent(payload) {
  const { event, data } = payload;
  console.log('[WebSocket Event]', event, data);

  switch (event) {
    case 'NEW_PRESCRIPTION':
      onNewPrescriptionReceived(data);
      break;

    case 'PRESCRIPTION_DISPENSED':
      onPrescriptionDispensed(data);
      break;

    case 'STOCK_UPDATED':
      onStockUpdated(data);
      break;

    case 'REMINDER_TOGGLED':
      if (typeof refreshReminders === 'function') {
        refreshReminders();
      }
      break;

    default:
      break;
  }
}

function onNewPrescriptionReceived(data) {
  playNotificationSound();
  unreadPrescriptionsCount++;
  updateNavbarBadge();

  showToast(`🔔 New Prescription: ${data.slip_number} for ${data.patient_name} ($${data.grand_total.toFixed(2)})`, 'success');

  // Prepend to live queue
  const newEntry = {
    slip_number: data.slip_number,
    patient_name: data.patient_name,
    patient_phone: data.patient_phone,
    doctor_name: data.doctor_name,
    diagnosis: data.diagnosis,
    grand_total: data.grand_total,
    created_at: data.created_at,
    status: 'RECEIVED',
    is_locked: false,
    cryptographic_lock: null,
    store_type: currentStoreMode,
    is_generic_substituted: false,
    generic_savings: 15.0,
    savings_percent: 78.5,
    items_count: data.items_count,
    items: [],
    substitutions: []
  };

  cachedQueue.unshift(newEntry);
  renderPharmacyQueue();
}

function onPrescriptionDispensed(data) {
  showToast(`✅ Prescription ${data.slip_number} dispensed at ${data.store_type} Store!`, 'info');
  // Update in cached queue
  const found = cachedQueue.find(q => q.slip_number === data.slip_number);
  if (found) {
    found.status = 'DISPENSED';
    found.is_locked = true;
    found.cryptographic_lock = data.cryptographic_lock;
    renderPharmacyQueue();
  }
}

function onStockUpdated(data) {
  const stockItem = cachedInventory.find(it => it.id === data.medicine_id);
  if (stockItem) {
    stockItem.stock_quantity = data.new_stock;
    stockItem.status = data.is_low_stock ? 'LOW_STOCK' : 'IN_STOCK';
    renderInventoryTable();
  }
}

function updateNavbarBadge() {
  const badge = document.getElementById('pharmacy-nav-badge');
  if (badge) {
    if (unreadPrescriptionsCount > 0) {
      badge.textContent = `${unreadPrescriptionsCount} New`;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  }
}

// Web Audio API synthesized notification sound (zero external mp3 dependency)
function playNotificationSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.12); // A5

    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.36);
  } catch (e) {
    // AudioContext might be restricted until user interaction
  }
}

// ==============================================================
// 2. URBAN VS RURAL MODE TOGGLING
// ==============================================================

function setStoreMode(mode) {
  currentStoreMode = mode;

  // Toggle UI buttons
  const btnUrban = document.getElementById('btn-mode-urban');
  const btnRural = document.getElementById('btn-mode-rural');
  if (btnUrban && btnRural) {
    if (mode === 'URBAN') {
      btnUrban.classList.add('active');
      btnRural.classList.remove('active');
    } else {
      btnRural.classList.add('active');
      btnUrban.classList.remove('active');
    }
  }

  // Toggle contextual banner
  const bannerUrban = document.getElementById('banner-urban-mode');
  const bannerRural = document.getElementById('banner-rural-mode');
  if (bannerUrban && bannerRural) {
    bannerUrban.style.display = mode === 'URBAN' ? 'block' : 'none';
    bannerRural.style.display = mode === 'RURAL' ? 'block' : 'none';
  }

  renderPharmacyQueue();
}

// ==============================================================
// 3. DATA FETCHING & RENDERING
// ==============================================================

async function loadPharmacyData() {
  try {
    // 1. Fetch queue
    const queueRes = await API.getPharmacyQueue(currentStoreMode);
    cachedQueue = queueRes.queue || [];
    renderPharmacyQueue();

    // 2. Fetch inventory
    const invRes = await API.getPharmacyInventory();
    cachedInventory = invRes.items || [];
    renderInventoryTable();
    updateInventoryMetrics(invRes);
  } catch (err) {
    console.warn('Error loading pharmacy data:', err);
  }
}

function renderPharmacyQueue() {
  const container = document.getElementById('pharmacy-queue-list');
  if (!container) return;

  if (cachedQueue.length === 0) {
    container.innerHTML = `
      <div class="empty-state-card">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>
        </svg>
        <h4>No Pending Prescriptions</h4>
        <p>When a doctor issues a clinical health slip, it will arrive here live in real time!</p>
      </div>
    `;
    return;
  }

  container.innerHTML = cachedQueue.map(item => {
    const isDispensed = item.status === 'DISPENSED';
    const isLocked = item.is_locked;
    const isRural = currentStoreMode === 'RURAL';

    // Build items display
    const itemsHtml = (item.items || []).map(it => `
      <div class="queue-item-row">
        <span>💊 <strong>${escapeHtml(it.item_name)}</strong> (x${it.quantity})</span>
        <span>$${it.total_price.toFixed(2)}</span>
      </div>
    `).join('');

    // Generic drug savings highlight for rural mode
    const savingsHtml = (isRural && item.generic_savings > 0) ? `
      <div class="generic-savings-badge">
        <div class="savings-tag">🌾 Jan Aushadhi Generic Savings</div>
        <div class="savings-amount">Save $${item.generic_savings.toFixed(2)} (${item.savings_percent}% Cheaper)</div>
        <div class="savings-subtext">Government-certified bio-equivalent generic salts available for this prescription.</div>
      </div>
    ` : '';

    // Action buttons depending on mode and status
    let actionButtons = '';
    if (isDispensed) {
      actionButtons = `
        <div class="dispensed-status-banner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></svg>
          DISPENSED & CRYPTOGRAPHICALLY LOCKED
          <span class="lock-hash-preview" title="${item.cryptographic_lock || ''}">${(item.cryptographic_lock || '').substring(0, 16)}...</span>
        </div>
      `;
    } else {
      actionButtons = `
        <div class="queue-actions-row">
          ${isRural ? `
            <button class="btn-pharmacy-substitute" onclick="substituteAndDispense('${item.slip_number}', true)">
              🌾 Dispense Generic Salt (Save ${item.savings_percent || 80}%)
            </button>
          ` : `
            <button class="btn-pharmacy-dispense" onclick="dispenseRx('${item.slip_number}', false)">
              🏢 Dispense & Lock Prescription
            </button>
          `}
          
          <button class="btn-pharmacy-audio" onclick="playAudioDosage('${item.slip_number}')" title="Play Voice Dosage for Patient">
            🔊 Voice Explainer
          </button>

          ${isRural ? `
            <button class="btn-pharmacy-sms" onclick="generateRuralSms('${item.slip_number}')" title="Copy SMS for 2G Keypad Phones">
              📱 2G SMS Slip
            </button>
          ` : ''}
        </div>
      `;
    }

    return `
      <div class="pharmacy-card ${isDispensed ? 'dispensed' : ''}">
        <div class="pharmacy-card-header">
          <div>
            <div class="card-slip-number">${escapeHtml(item.slip_number)}</div>
            <div class="card-patient-info">
              👤 <strong>${escapeHtml(item.patient_name)}</strong> • 📞 ${escapeHtml(item.patient_phone)}
            </div>
            <div class="card-doc-info">
              👨‍⚕️ ${escapeHtml(item.doctor_name)} • 🩺 ${escapeHtml(item.diagnosis)}
            </div>
          </div>
          <div class="card-header-right">
            <span class="status-badge ${isDispensed ? 'status-dispensed' : 'status-pending'}">
              ${isDispensed ? 'COMPLETED' : 'AWAITING DISPENSE'}
            </span>
            <div class="card-total-price">$${item.grand_total.toFixed(2)}</div>
          </div>
        </div>

        ${savingsHtml}

        <div class="card-items-section">
          ${itemsHtml || '<div style="color: var(--text-muted); font-size: 0.85rem;">Prescribed medications ready for fulfillment</div>'}
        </div>

        ${actionButtons}
      </div>
    `;
  }).join('');
}

function renderInventoryTable() {
  const tbody = document.getElementById('pharmacy-inventory-tbody');
  if (!tbody) return;

  tbody.innerHTML = cachedInventory.map(item => {
    const isLow = item.status === 'LOW_STOCK';
    const isOut = item.status === 'OUT_OF_STOCK';

    let badgeClass = 'badge-stock-in';
    let badgeText = 'In Stock';
    if (isOut) {
      badgeClass = 'badge-stock-out';
      badgeText = 'Out of Stock';
    } else if (isLow) {
      badgeClass = 'badge-stock-low';
      badgeText = 'Low Stock';
    }

    return `
      <tr>
        <td>
          <strong>${escapeHtml(item.brand_name)}</strong>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(item.generic_name)}</div>
        </td>
        <td><code style="font-size: 0.75rem;">${escapeHtml(item.batch_number)}</code></td>
        <td>
          <span class="stock-pill ${badgeClass}">
            ${item.stock_quantity} units
          </span>
          <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Min: ${item.reorder_level}</div>
        </td>
        <td>
          <div style="font-weight: 600;">$${item.unit_price_brand.toFixed(2)}</div>
          <div style="font-size: 0.75rem; color: var(--success); font-weight: 500;">
            Generic: $${item.unit_price_generic.toFixed(2)} (${item.savings_percent}% off)
          </div>
        </td>
        <td>
          <button class="btn-quick-adjust" onclick="adjustMedicineStock(${item.id}, 20)" title="Add 20 units">+20</button>
          <button class="btn-quick-adjust" onclick="adjustMedicineStock(${item.id}, -10)" title="Deduct 10 units">-10</button>
        </td>
      </tr>
    `;
  }).join('');
}

function updateInventoryMetrics(invRes) {
  const totalEl = document.getElementById('inv-metric-total');
  const lowEl = document.getElementById('inv-metric-low');
  if (totalEl) totalEl.textContent = invRes.total_items;
  if (lowEl) lowEl.textContent = invRes.low_stock_count;
}

// ==============================================================
// 4. PHARMACY ACTIONS: DISPENSE & ANTI-DOUBLE DISPENSING LOCK
// ==============================================================

async function dispenseRx(slipNumber, isGeneric) {
  try {
    const pharmacistName = currentStoreMode === 'RURAL' 
      ? 'Rural Seva Health Pharmacist' 
      : 'Urban Medical Store Dispenser';

    // Check if offline
    if (!navigator.onLine) {
      queueOfflineDispense(slipNumber, isGeneric, pharmacistName);
      return;
    }

    const payload = {
      slip_number: slipNumber,
      store_type: currentStoreMode,
      pharmacist_name: pharmacistName,
      is_generic_substituted: isGeneric,
      notes: `Dispensed at ${currentStoreMode} counter with cryptographic verification.`
    };

    const res = await API.dispensePrescription(payload);
    if (res.success) {
      showToast(`Prescription ${slipNumber} DISPENSED & SEALED cryptographically!`, 'success');
      loadPharmacyData();
    }
  } catch (err) {
    showToast(`Dispense error: ${err.message}`, 'error');
  }
}

async function substituteAndDispense(slipNumber) {
  const confirmed = confirm("Switch to Jan Aushadhi Low-Cost Generic Equivalent? This reduces medication cost by ~80% for the rural patient.");
  if (confirmed) {
    await dispenseRx(slipNumber, true);
  }
}

async function adjustMedicineStock(medicineId, amount) {
  try {
    const res = await API.adjustStock(medicineId, amount);
    if (res.success) {
      showToast(`Updated stock: ${res.brand_name} now ${res.stock_quantity} units.`, 'info');
      loadPharmacyData();
    }
  } catch (err) {
    showToast(`Stock error: ${err.message}`, 'error');
  }
}

// ==============================================================
// 5. VERNACULAR AUDIO DOSAGE & MULTILINGUAL TTS
// ==============================================================

async function playAudioDosage(slipNumber) {
  const item = cachedQueue.find(q => q.slip_number === slipNumber);
  const medName = (item && item.items && item.items[0]) ? item.items[0].item_name : 'Ibuprofen';

  // Ask language preference (Hindi for rural vernacular, or English)
  const lang = (currentStoreMode === 'RURAL') ? 'hi' : 'en';

  try {
    const res = await API.getAudioDosageScript(medName, lang);
    const speechText = res.speech_text;

    // Show modal or speech card
    showVoiceModal(res.medicine_name, speechText, res.timing_glyph, lang);

    // Trigger Browser SpeechSynthesis
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel(); // Stop any previous speech
      const utterance = new SpeechSynthesisUtterance(speechText);
      utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-US';
      utterance.rate = 0.9; // Speak clearly for rural patients
      window.speechSynthesis.speak(utterance);
    }
  } catch (err) {
    showToast(`Voice player error: ${err.message}`, 'error');
  }
}

function showVoiceModal(medicine, text, glyph, lang) {
  let modal = document.getElementById('voice-dosage-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'voice-dosage-modal';
    modal.className = 'custom-modal-backdrop';
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div class="custom-modal-dialog">
      <div class="voice-modal-header">
        <div style="font-size: 2.2rem;">${glyph || '🌅'}</div>
        <div>
          <h3>🔊 Vernacular Voice Dosage Explainer</h3>
          <p style="margin: 0; color: var(--text-muted); font-size: 0.85rem;">Designed for rural patients & illiterate accessibility</p>
        </div>
      </div>

      <div class="voice-modal-body">
        <div class="voice-medicine-name">${escapeHtml(medicine)}</div>
        <div class="voice-script-box">
          "${escapeHtml(text)}"
        </div>
        <div class="voice-language-indicator">
          🌐 Language: <strong>${lang === 'hi' ? 'Hindi (हिन्दी)' : 'English'}</strong>
        </div>
      </div>

      <div class="voice-modal-actions">
        <button class="btn-voice-replay" onclick="repeatVoiceSpeech('${escapeHtml(text)}', '${lang}')">
          🔁 Speak Again
        </button>
        <button class="btn-voice-close" onclick="closeVoiceModal()">
          Close
        </button>
      </div>
    </div>
  `;

  modal.style.display = 'flex';
}

function repeatVoiceSpeech(text, lang) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-US';
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  }
}

function closeVoiceModal() {
  const modal = document.getElementById('voice-dosage-modal');
  if (modal) modal.style.display = 'none';
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

// ==============================================================
// 6. RURAL 2G KEYPAD PHONE SMS GENERATOR
// ==============================================================

async function generateRuralSms(slipNumber) {
  try {
    const res = await API.getRuralSmsSlip(slipNumber);
    const smsContent = res.sms_content;

    // Copy to clipboard
    navigator.clipboard.writeText(smsContent);
    showToast(`📋 Copied 2G SMS Slip (${res.char_count} chars): "${smsContent}"`, 'success');
  } catch (err) {
    showToast(`SMS error: ${err.message}`, 'error');
  }
}

// ==============================================================
// 7. OFFLINE-FIRST SYNCHRONIZATION (RURAL LOW-BANDWIDTH)
// ==============================================================

function initNetworkListeners() {
  window.addEventListener('online', () => {
    showToast('🌐 Internet connection restored! Syncing offline records...', 'success');
    updateRealtimeBadge(true);
    syncOfflineQueue();
  });

  window.addEventListener('offline', () => {
    showToast('⚠️ No internet connection detected. Switching to Rural Offline Mode.', 'warning');
    updateRealtimeBadge(false);
  });
}

function queueOfflineDispense(slipNumber, isGeneric, pharmacistName) {
  const queue = JSON.parse(localStorage.getItem('healthslip_offline_queue') || '[]');
  queue.push({
    slip_number: slipNumber,
    is_generic_substituted: isGeneric,
    pharmacist_name: pharmacistName,
    store_type: currentStoreMode,
    timestamp: new Date().toISOString()
  });
  localStorage.setItem('healthslip_offline_queue', JSON.stringify(queue));

  showToast(`⚠️ Stored offline! Prescription ${slipNumber} will sync automatically when online.`, 'warning');

  // Mark locally as dispensed
  const found = cachedQueue.find(q => q.slip_number === slipNumber);
  if (found) {
    found.status = 'DISPENSED';
    found.is_locked = true;
    found.cryptographic_lock = 'OFFLINE_PENDING_SYNC';
    renderPharmacyQueue();
  }
}

async function syncOfflineQueue() {
  const raw = localStorage.getItem('healthslip_offline_queue');
  if (!raw) return;

  const queue = JSON.parse(raw);
  if (queue.length === 0) return;

  console.log(`[Offline Sync] Flushing ${queue.length} pending dispenses to server...`);
  const remaining = [];

  for (const item of queue) {
    try {
      await API.dispensePrescription({
        slip_number: item.slip_number,
        store_type: item.store_type,
        pharmacist_name: item.pharmacist_name,
        is_generic_substituted: item.is_generic_substituted,
        notes: `Synced from Rural Offline Queue (originally queued at ${item.timestamp})`
      });
    } catch (e) {
      console.warn(`Failed to sync item ${item.slip_number}:`, e);
      remaining.push(item);
    }
  }

  localStorage.setItem('healthslip_offline_queue', JSON.stringify(remaining));
  if (remaining.length === 0) {
    showToast(`✅ All offline dispenses synced successfully!`, 'success');
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[m]));
}
