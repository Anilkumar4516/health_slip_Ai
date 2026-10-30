// HealthSlip AI - Real-World Medical Store & Clinical Pharmacy POS Controller

let currentStoreMode = 'URBAN'; // 'URBAN' or 'RURAL'
let realtimeSocket = null;
let realtimeReconnectTimer = null;
let unreadPrescriptionsCount = 0;
let cachedQueue = [];
let cachedInventory = [];
let activeQueueFilter = 'ALL'; // 'ALL', 'PENDING', 'DISPENSED'
let currentSearchTerm = '';
let currentInventorySearchTerm = '';

document.addEventListener('DOMContentLoaded', () => {
  initRealtimeWebSocket();
  initNetworkListeners();
  loadPharmacyData();
});

// ==============================================================
// 1. REAL-TIME WEBSOCKET SYNCHRONIZATION (REDIS / SCALED HUB)
// ==============================================================

let realtimeSocket = null;
let realtimeReconnectTimer = null;
let realtimeHeartbeatTimer = null;
let reconnectBackoffMs = 2000;

function initRealtimeWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const token = localStorage.getItem('healthslip_token') || localStorage.getItem('healthslip_access_token') || '';
  const storeId = window.currentStoreId || (currentStoreMode === 'RURAL' ? 2 : 1);
  const wsUrl = `${protocol}//${window.location.host}/ws/live?token=${encodeURIComponent(token)}&store_id=${storeId}`;

  try {
    if (realtimeSocket) {
      try { realtimeSocket.close(); } catch (_) {}
    }

    realtimeSocket = new WebSocket(wsUrl);

    realtimeSocket.onopen = () => {
      console.log('[WebSocket] Connected to HealthSlip AI Real-Time Hub (Store Room: ' + storeId + ')');
      reconnectBackoffMs = 2000; // Reset backoff on success
      updateRealtimeBadge(true);

      // Start 25s Heartbeat Ping/Pong
      if (realtimeHeartbeatTimer) clearInterval(realtimeHeartbeatTimer);
      realtimeHeartbeatTimer = setInterval(() => {
        if (realtimeSocket && realtimeSocket.readyState === WebSocket.OPEN) {
          realtimeSocket.send(JSON.stringify({ event: 'PING', timestamp: Date.now() }));
        }
      }, 25000);

      // Sync any staged offline transactions
      syncOfflineQueue();
    };

    realtimeSocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.event === 'PONG') {
          return; // Heartbeat healthy
        }
        handleRealtimeEvent(message);
      } catch (err) {
        console.warn('[WebSocket] Error parsing event:', err);
      }
    };

    realtimeSocket.onclose = () => {
      if (realtimeHeartbeatTimer) clearInterval(realtimeHeartbeatTimer);
      console.warn(`[WebSocket] Disconnected from server. Reconnecting in ${(reconnectBackoffMs / 1000).toFixed(1)}s...`);
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
  }, reconnectBackoffMs);
  // Exponential backoff with jitter up to 30 seconds
  reconnectBackoffMs = Math.min(30000, Math.floor(reconnectBackoffMs * 1.5 + Math.random() * 500));
}

function updateRealtimeBadge(isConnected) {
  const badgeEl = document.getElementById('pharmacy-realtime-badge');
  const dotEl = document.getElementById('pharmacy-realtime-dot');
  const textEl = document.getElementById('pharmacy-realtime-text');

  if (badgeEl && dotEl && textEl) {
    if (isConnected) {
      badgeEl.className = 'realtime-status-pill online';
      dotEl.className = 'status-pulse-dot green';
      textEl.textContent = 'Counter Live: Connected';
    } else {
      badgeEl.className = 'realtime-status-pill offline';
      dotEl.className = 'status-pulse-dot red';
      textEl.textContent = navigator.onLine ? 'Reconnecting...' : 'Offline (Local Queue)';
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

  showToast(`🔔 New Rx ${data.slip_number} for ${data.patient_name} (₹${data.grand_total.toFixed(2)})`, 'success');

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
    generic_savings: 14.7,
    savings_percent: 79.5,
    items_count: data.items_count,
    items: [],
    substitutions: []
  };

  cachedQueue.unshift(newEntry);
  renderPharmacyQueue();
}

function onPrescriptionDispensed(data) {
  showToast(`✅ Rx ${data.slip_number} dispensed at ${data.store_type} Store!`, 'info');
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
  } else {
    // If newly added item
    loadPharmacyData();
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

function playNotificationSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.12);

    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.36);
  } catch (e) {
    // Audio restricted before user gesture
  }
}

// ==============================================================
// 2. STORE MODE SWITCHER
// ==============================================================

function setStoreMode(mode) {
  currentStoreMode = mode;

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

  const bannerUrban = document.getElementById('banner-urban-mode');
  const bannerRural = document.getElementById('banner-rural-mode');
  if (bannerUrban && bannerRural) {
    bannerUrban.style.display = mode === 'URBAN' ? 'flex' : 'none';
    bannerRural.style.display = mode === 'RURAL' ? 'flex' : 'none';
  }

  renderPharmacyQueue();
}

// ==============================================================
// 3. DATA FETCHING & RENDERING
// ==============================================================

async function loadPharmacyData() {
  try {
    const queueRes = await API.getPharmacyQueue(currentStoreMode);
    cachedQueue = queueRes.queue || [];
    renderPharmacyQueue();

    const invRes = await API.getPharmacyInventory();
    cachedInventory = invRes.items || [];
    renderInventoryTable();
    updateInventoryMetrics(invRes);
  } catch (err) {
    console.warn('Error loading pharmacy data:', err);
  }
}

function applyQueueFilter(filterType) {
  activeQueueFilter = filterType;
  document.querySelectorAll('.filter-pill').forEach(btn => btn.classList.remove('active'));
  if (filterType === 'ALL') document.getElementById('filter-all-btn')?.classList.add('active');
  if (filterType === 'PENDING') document.getElementById('filter-pending-btn')?.classList.add('active');
  if (filterType === 'DISPENSED') document.getElementById('filter-dispensed-btn')?.classList.add('active');
  renderPharmacyQueue();
}

function filterPharmacyQueue() {
  const input = document.getElementById('pharmacy-search-input');
  currentSearchTerm = (input ? input.value : '').trim().toLowerCase();
  renderPharmacyQueue();
}

function loadSlipByBarcode() {
  const input = document.getElementById('barcode-slip-input');
  const slipNo = (input ? input.value : '').trim().toUpperCase();
  if (!slipNo) {
    showToast('Please enter or scan a valid Slip ID (e.g. HSL-2026-94670)', 'warning');
    return;
  }

  const found = cachedQueue.find(q => q.slip_number.toUpperCase() === slipNo);
  if (found) {
    showToast(`Rx ${slipNo} found! Loaded to dispensing counter.`, 'success');
    if (input) input.value = '';
    // Scroll to the card
    const searchInput = document.getElementById('pharmacy-search-input');
    if (searchInput) searchInput.value = slipNo;
    filterPharmacyQueue();
  } else {
    showToast(`Prescription ${slipNo} not found in current counter queue.`, 'error');
  }
}

function renderPharmacyQueue() {
  const container = document.getElementById('pharmacy-queue-list');
  const countEl = document.getElementById('queue-visible-count');
  if (!container) return;

  // Filter items based on active status filter and search term
  let filtered = cachedQueue.filter(item => {
    // Status filter
    if (activeQueueFilter === 'PENDING' && item.status === 'DISPENSED') return false;
    if (activeQueueFilter === 'DISPENSED' && item.status !== 'DISPENSED') return false;

    // Search filter
    if (currentSearchTerm) {
      const matchSlip = item.slip_number.toLowerCase().includes(currentSearchTerm);
      const matchPatient = (item.patient_name || '').toLowerCase().includes(currentSearchTerm);
      const matchPhone = (item.patient_phone || '').includes(currentSearchTerm);
      const matchDoc = (item.doctor_name || '').toLowerCase().includes(currentSearchTerm);
      const matchDiag = (item.diagnosis || '').toLowerCase().includes(currentSearchTerm);
      const matchItem = (item.items || []).some(it => (it.item_name || '').toLowerCase().includes(currentSearchTerm));
      return matchSlip || matchPatient || matchPhone || matchDoc || matchDiag || matchItem;
    }
    return true;
  });

  if (countEl) countEl.textContent = filtered.length;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state-card">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>
        </svg>
        <h4>No Prescriptions Found</h4>
        <p>No matching prescriptions in counter queue. Use the Doctor Slip Builder to issue new clinical prescriptions!</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(item => {
    const isDispensed = item.status === 'DISPENSED';
    const isRural = currentStoreMode === 'RURAL';

    const itemsHtml = (item.items || []).map(it => `
      <div class="queue-item-row">
        <span>💊 <strong>${escapeHtml(it.item_name)}</strong> (x${it.quantity})</span>
        <span style="font-weight: 600;">₹${it.total_price.toFixed(2)}</span>
      </div>
    `).join('');

    const savingsHtml = (isRural && item.generic_savings > 0) ? `
      <div class="generic-savings-badge">
        <div class="savings-tag">🌾 Jan Aushadhi Generic Savings</div>
        <div class="savings-amount">Patient Saves ₹${item.generic_savings.toFixed(2)} (${item.savings_percent}% Cheaper)</div>
        <div class="savings-subtext">Certified bio-equivalent generic salts available for this prescription.</div>
      </div>
    ` : '';

    let actionButtons = '';
    if (isDispensed) {
      actionButtons = `
        <div class="dispensed-status-banner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></svg>
          DISPENSED & CRYPTOGRAPHICALLY LOCKED
          <span class="lock-hash-preview" title="${item.cryptographic_lock || ''}">${(item.cryptographic_lock || '').substring(0, 16)}...</span>
        </div>
        <div class="queue-actions-row" style="margin-top: 0.6rem;">
          <button class="btn-pharmacy-memo" onclick="openPharmacyInvoiceModal('${item.slip_number}')">
            🧾 View Pharmacy Cash Memo / Invoice
          </button>
          <button class="btn-pharmacy-audio" onclick="playAudioDosage('${item.slip_number}')" title="Play Voice Dosage">
            🔊 Voice Explainer
          </button>
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
          
          <button class="btn-pharmacy-memo" onclick="openPharmacyInvoiceModal('${item.slip_number}')" title="Preview Pharmacy Cash Memo">
            🧾 Cash Memo
          </button>

          <button class="btn-pharmacy-audio" onclick="playAudioDosage('${item.slip_number}')" title="Play Voice Dosage for Patient">
            🔊 Voice
          </button>

          ${isRural ? `
            <button class="btn-pharmacy-sms" onclick="generateRuralSms('${item.slip_number}')" title="Copy SMS for 2G Keypad Phones">
              📱 2G SMS
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
              ${isDispensed ? 'DISPENSED' : 'READY TO DISPENSE'}
            </span>
            <div class="card-total-price">₹${item.grand_total.toFixed(2)}</div>
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

// ==============================================================
// 4. INVENTORY MANAGEMENT & REAL-TIME SEARCH
// ==============================================================

function filterInventoryTable() {
  const input = document.getElementById('inventory-search-input');
  currentInventorySearchTerm = (input ? input.value : '').trim().toLowerCase();
  renderInventoryTable();
}

function renderInventoryTable() {
  const tbody = document.getElementById('pharmacy-inventory-tbody');
  if (!tbody) return;

  let filtered = cachedInventory.filter(item => {
    if (!currentInventorySearchTerm) return true;
    const matchBrand = (item.brand_name || '').toLowerCase().includes(currentInventorySearchTerm);
    const matchGeneric = (item.generic_name || '').toLowerCase().includes(currentInventorySearchTerm);
    const matchBatch = (item.batch_number || '').toLowerCase().includes(currentInventorySearchTerm);
    return matchBrand || matchGeneric || matchBatch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; padding: 1.5rem; color: var(--text-muted);">
          No medicine batches found matching "${escapeHtml(currentInventorySearchTerm)}".
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(item => {
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
          <strong style="color: var(--text-main); font-size: 0.82rem;">${escapeHtml(item.brand_name)}</strong>
          <div style="font-size: 0.72rem; color: var(--primary); font-weight: 500;">${escapeHtml(item.generic_name)}</div>
        </td>
        <td>
          <code style="font-size: 0.72rem; background: #f1f5f9; padding: 2px 4px; border-radius: 4px;">${escapeHtml(item.batch_number)}</code>
          <div style="font-size: 0.68rem; color: var(--text-dim); margin-top: 2px;">Exp: 11/2027</div>
        </td>
        <td>
          <span class="stock-pill ${badgeClass}">
            ${item.stock_quantity} units
          </span>
          <div style="font-size: 0.68rem; color: var(--text-muted); margin-top: 2px;">Min: ${item.reorder_level}</div>
        </td>
        <td>
          <div style="font-weight: 600; font-size: 0.8rem;">₹${item.unit_price_brand.toFixed(2)}</div>
          <div style="font-size: 0.72rem; color: var(--emerald-text); font-weight: 600;">
            Generic: ₹${item.unit_price_generic.toFixed(2)} (${item.savings_percent}% off)
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

// Add New Medicine Batch Modal Handlers
function openAddMedicineModal() {
  const modal = document.getElementById('add-medicine-modal');
  if (modal) modal.style.display = 'flex';
}

function closeAddMedicineModal() {
  const modal = document.getElementById('add-medicine-modal');
  if (modal) modal.style.display = 'none';
}

async function submitNewMedicine(event) {
  event.preventDefault();
  const brand = document.getElementById('add-med-brand').value;
  const generic = document.getElementById('add-med-generic').value;
  const form = document.getElementById('add-med-form').value;
  const strength = document.getElementById('add-med-strength').value || '500mg';
  const batch = document.getElementById('add-med-batch').value;
  const qty = parseInt(document.getElementById('add-med-qty').value, 10);
  const brandPrice = parseFloat(document.getElementById('add-med-brand-price').value);
  const genericPrice = parseFloat(document.getElementById('add-med-generic-price').value);
  const te = document.getElementById('add-med-te')?.value || document.getElementById('add-med-hi')?.value || "భోజనం తర్వాత నీటితో తీసుకోండి";

  try {
    const payload = {
      brand_name: brand,
      generic_name: generic,
      dosage_form: form,
      strength: strength,
      batch_number: batch,
      stock_quantity: qty,
      reorder_level: 15,
      unit_price_brand: brandPrice,
      unit_price_generic: genericPrice,
      vernacular_dosage_te: te,
      vernacular_dosage_hi: te,
      vernacular_dosage_en: "Take after meals with water",
      visual_timing: "AFTER_MEAL"
    };

    const res = await API.addMedicine(payload);
    if (res.success) {
      showToast(`Medicine batch ${batch} added to inventory successfully!`, 'success');
      closeAddMedicineModal();
      document.getElementById('add-medicine-form').reset();
      loadPharmacyData();
    }
  } catch (err) {
    showToast(`Error adding medicine: ${err.message}`, 'error');
  }
}

// ==============================================================
// 5. OFFICIAL MEDICAL STORE THERMAL CASH MEMO MODAL
// ==============================================================

async function openPharmacyInvoiceModal(slipNumber) {
  try {
    const bill = await API.getPharmacyBill(slipNumber);
    const modal = document.getElementById('pharmacy-invoice-modal');
    if (!modal) return;

    // Header info
    document.getElementById('memo-store-name').textContent = bill.store_info.name;
    document.getElementById('memo-store-sub').innerHTML = `
      ${bill.store_info.dl_number} • GSTIN: ${bill.store_info.gstin}<br>
      ${bill.store_info.address} • ${bill.store_info.pharmacist}
    `;

    // Meta details
    document.getElementById('memo-meta-details').innerHTML = `
      <div><strong>Inv #:</strong> ${bill.invoice_number}</div>
      <div><strong>Date:</strong> ${bill.date}</div>
      <div><strong>Patient:</strong> ${escapeHtml(bill.patient.name)} (${bill.patient.age}/${bill.patient.gender})</div>
      <div><strong>Phone:</strong> ${escapeHtml(bill.patient.phone)}</div>
      <div><strong>Doctor:</strong> ${escapeHtml(bill.doctor.name)}</div>
      <div><strong>Lic #:</strong> ${escapeHtml(bill.doctor.license)}</div>
    `;

    // Table items
    const tbody = document.getElementById('memo-items-tbody');
    tbody.innerHTML = bill.items.map(it => `
      <tr>
        <td>
          <strong>${escapeHtml(it.name)}</strong>
          ${it.savings > 0 ? `<div style="font-size: 0.65rem; color: #15803d; font-weight: 600;">Jan Aushadhi Generic</div>` : ''}
        </td>
        <td><code>${escapeHtml(it.batch)}</code></td>
        <td style="text-align: center;">${it.quantity}</td>
        <td>₹${it.unit_price.toFixed(2)}</td>
        <td style="font-weight: 700;">₹${it.total_price.toFixed(2)}</td>
      </tr>
    `).join('');

    // Totals
    document.getElementById('memo-totals-section').innerHTML = `
      <div class="thermal-totals-row">
        <span>MRP Value:</span>
        <span>₹${bill.financials.mrp_total.toFixed(2)}</span>
      </div>
      ${bill.financials.jan_aushadhi_savings > 0 ? `
        <div class="thermal-totals-row savings">
          <span>Jan Aushadhi Generic Savings:</span>
          <span>-₹${bill.financials.jan_aushadhi_savings.toFixed(2)}</span>
        </div>
      ` : ''}
      <div class="thermal-totals-row">
        <span>Taxable Subtotal:</span>
        <span>₹${bill.financials.subtotal.toFixed(2)}</span>
      </div>
      <div class="thermal-totals-row">
        <span>GST (${bill.financials.tax_rate}%):</span>
        <span>₹${bill.financials.tax_amount.toFixed(2)}</span>
      </div>
      <div class="thermal-totals-row grand">
        <span>NET PAYABLE:</span>
        <span>₹${bill.financials.grand_total.toFixed(2)}</span>
      </div>
    `;

    // Seal box
    document.getElementById('memo-seal-box').innerHTML = `
      <div class="seal-hash-title">HMAC-SHA256 Cryptographic Dispense Seal:</div>
      <div class="seal-hash-text">${bill.cryptographic_seal}</div>
      <div class="seal-verify-note">Verified & Registered on HealthSlip AI Pharmacy Network</div>
    `;

    modal.style.display = 'flex';
  } catch (err) {
    showToast(`Error loading pharmacy bill: ${err.message}`, 'error');
  }
}

function closePharmacyInvoiceModal() {
  const modal = document.getElementById('pharmacy-invoice-modal');
  if (modal) modal.style.display = 'none';
}

// ==============================================================
// 6. PHARMACY ACTIONS: DISPENSE & ANTI-DOUBLE DISPENSING LOCK
// ==============================================================

async function dispenseRx(slipNumber, isGeneric) {
  try {
    const pharmacistName = currentStoreMode === 'RURAL' 
      ? 'Rural Seva Health Pharmacist' 
      : 'Urban Medical Store Dispenser';

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
      showToast(`Prescription ${slipNumber} DISPENSED & SEALED!`, 'success');
      loadPharmacyData();
      // Open thermal memo immediately for printing
      openPharmacyInvoiceModal(slipNumber);
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
// 7. VERNACULAR AUDIO DOSAGE & MULTILINGUAL TTS
// ==============================================================

async function playAudioDosage(slipNumber, chosenLang) {
  const item = cachedQueue.find(q => q.slip_number === slipNumber);
  const medName = (item && item.items && item.items[0]) ? item.items[0].item_name : 'Crocin 650mg';
  const lang = chosenLang || (currentStoreMode === 'RURAL' ? 'te' : 'en');

  try {
    const res = await API.getAudioDosageScript(medName, lang);
    const speechText = res.speech_text;

    showVoiceModal(res.medicine_name, speechText, res.timing_glyph, lang, slipNumber);

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(speechText);
      utterance.lang = lang === 'te' ? 'te-IN' : 'en-US';
      utterance.rate = 0.88;

      // Try selecting a matching Telugu voice if available on user device
      const voices = window.speechSynthesis.getVoices();
      if (lang === 'te') {
        const teVoice = voices.find(v => v.lang.startsWith('te') || v.name.toLowerCase().includes('telugu'));
        if (teVoice) utterance.voice = teVoice;
      }
      window.speechSynthesis.speak(utterance);
    }
  } catch (err) {
    showToast(`Voice player error: ${err.message}`, 'error');
  }
}

function showVoiceModal(medicine, text, glyph, lang, slipNumber) {
  let modal = document.getElementById('voice-dosage-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'voice-dosage-modal';
    modal.className = 'custom-modal-backdrop';
    document.body.appendChild(modal);
  }

  const safeText = escapeHtml(text).replace(/'/g, "\\'");
  const currentSlip = slipNumber || '';

  modal.innerHTML = `
    <div class="custom-modal-dialog">
      <div class="voice-modal-header">
        <div style="font-size: 2.2rem;">${glyph || '🌅'}</div>
        <div>
          <h3>🔊 Vernacular Voice Dosage Explainer</h3>
          <p style="margin: 0; color: var(--text-muted); font-size: 0.85rem;">Designed for rural patients & illiterate accessibility (Telugu & English)</p>
        </div>
      </div>

      <div class="voice-modal-body">
        <div class="voice-medicine-name">${escapeHtml(medicine)}</div>
        <div class="voice-script-box" style="font-size: 1.05rem; line-height: 1.6; border-left: 4px solid var(--primary);">
          "${escapeHtml(text)}"
        </div>
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; background: #f8fafc; padding: 8px 12px; border-radius: 6px;">
          <div class="voice-language-indicator" style="margin: 0;">
            🌐 Active: <strong>${lang === 'te' ? 'Telugu (తెలుగు)' : 'English'}</strong>
          </div>
          <div style="display: flex; gap: 6px;">
            <button class="btn-voice-replay" style="padding: 4px 10px; font-size: 0.8rem; background: ${lang === 'te' ? 'var(--primary)' : '#e2e8f0'}; color: ${lang === 'te' ? '#fff' : '#1e293b'};" onclick="playAudioDosage('${currentSlip}', 'te')">
              తెలుగు (Telugu)
            </button>
            <button class="btn-voice-replay" style="padding: 4px 10px; font-size: 0.8rem; background: ${lang === 'en' ? 'var(--primary)' : '#e2e8f0'}; color: ${lang === 'en' ? '#fff' : '#1e293b'};" onclick="playAudioDosage('${currentSlip}', 'en')">
              English
            </button>
          </div>
        </div>
      </div>

      <div class="voice-modal-actions">
        <button class="btn-voice-replay" onclick="repeatVoiceSpeech('${safeText}', '${lang}')">
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
    utterance.lang = lang === 'te' ? 'te-IN' : 'en-US';
    utterance.rate = 0.88;
    const voices = window.speechSynthesis.getVoices();
    if (lang === 'te') {
      const teVoice = voices.find(v => v.lang.startsWith('te') || v.name.toLowerCase().includes('telugu'));
      if (teVoice) utterance.voice = teVoice;
    }
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
// 8. RURAL 2G KEYPAD PHONE SMS GENERATOR
// ==============================================================

async function generateRuralSms(slipNumber) {
  try {
    const res = await API.getRuralSmsSlip(slipNumber);
    const smsContent = res.sms_content;

    navigator.clipboard.writeText(smsContent);
    showToast(`📋 Copied 2G SMS Slip (${res.char_count} chars): "${smsContent}"`, 'success');
  } catch (err) {
    showToast(`SMS error: ${err.message}`, 'error');
  }
}

// ==============================================================
// 9. OFFLINE-FIRST SYNCHRONIZATION (RURAL LOW-BANDWIDTH)
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

function generateClientSyncId() {
  if (window.crypto && window.crypto.randomUUID) {
    return 'sync-' + window.crypto.randomUUID();
  }
  return 'sync-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

function queueOfflineDispense(slipNumber, isGeneric, pharmacistName) {
  const syncId = generateClientSyncId();
  const queue = JSON.parse(localStorage.getItem('healthslip_offline_queue') || '[]');
  queue.push({
    client_sync_id: syncId,
    slip_number: slipNumber,
    is_generic_substituted: isGeneric,
    pharmacist_name: pharmacistName,
    store_type: currentStoreMode,
    timestamp: new Date().toISOString()
  });
  localStorage.setItem('healthslip_offline_queue', JSON.stringify(queue));

  showToast(`⚠️ Staged offline (${syncId.slice(0, 13)}...). Final cryptographic dispense requires server connection to prevent double dispensing across stores.`, 'warning');

  const found = cachedQueue.find(q => q.slip_number === slipNumber);
  if (found) {
    found.status = 'PENDING_SYNC';
    found.is_locked = true;
    found.cryptographic_lock = 'OFFLINE_STAGED_AWAITING_SYNC';
    renderPharmacyQueue();
  }
  updateSyncPill();
}

async function syncOfflineQueue() {
  const raw = localStorage.getItem('healthslip_offline_queue');
  if (!raw) return;

  const queue = JSON.parse(raw);
  if (queue.length === 0) {
    updateSyncPill();
    return;
  }

  console.log(`[Offline Sync] Flushing ${queue.length} pending dispenses to server...`);
  const remaining = [];

  for (const item of queue) {
    try {
      await API.dispensePrescription({
        slip_number: item.slip_number,
        store_type: item.store_type,
        pharmacist_name: item.pharmacist_name,
        is_generic_substituted: item.is_generic_substituted,
        generic_substitution_confirmed: true,
        schedule_confirmed: true,
        client_sync_id: item.client_sync_id,
        notes: `Synced from Rural Offline Queue (idempotent sync ${item.client_sync_id}, queued ${item.timestamp})`
      });
      showToast(`✅ Synced & sealed prescription ${item.slip_number}`, 'success');
    } catch (e) {
      if (e.message && e.message.includes('ALREADY BEEN DISPENSED')) {
        showToast(`❌ Conflict: Prescription ${item.slip_number} was already dispensed at another store while offline! Cancelled.`, 'error');
      } else {
        console.warn(`Failed to sync item ${item.slip_number}:`, e);
        remaining.push(item);
      }
    }
  }

  localStorage.setItem('healthslip_offline_queue', JSON.stringify(remaining));
  updateSyncPill();
  if (remaining.length === 0) {
    loadPharmacyData();
  }
}

function updateSyncPill() {
  const queue = JSON.parse(localStorage.getItem('healthslip_offline_queue') || '[]');
  const textEl = document.getElementById('pharmacy-realtime-text');
  const badgeEl = document.getElementById('pharmacy-realtime-badge');
  if (queue.length > 0 && textEl) {
    textEl.textContent = `Sync Status: ${queue.length} Offline Staged`;
    if (badgeEl) badgeEl.className = 'realtime-status-pill warning';
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
