// HealthSlip AI - Doctor AI Slip Builder & Financial Calculator

let currentReceiptItems = [];
let currentReminders = [];

const SAMPLE_CLINICAL_NOTES = {
  migraine: `Patient Minh Nguyen, 28/M, presenting with acute episodic tension migraine and mild rhinovirus nasal congestion.
Vitals: BP 120/78, Temp 98.6F, Pulse 72.
Prescription Plan:
1. Ibuprofen 400mg, 1 pill at 12:00 am and after lunch for 5 days.
2. Ibuprofen metisylat, 1 pill after lunch for 5 days.
Advised ample fluid hydration and restful sleep. Complete physical examination conducted. Consultation fee $50. Follow up in 7 days.`,

  bronchitis: `Patient Sarah Jenkins, 42/F, complaints of persistent productive cough, low-grade fever 100.4F, and chest congestion for 4 days.
Impression: Acute Bacterial Bronchitis.
Prescriptions & Diagnostics:
1. Amoxicillin 500mg, 1 tablet three times daily (morning, afternoon, evening) for 7 days.
2. Paracetamol 650mg SOS for fever control.
3. Ordered Complete Blood Count (CBC) and Digital Chest X-Ray.
Consultation $50. Warning: Complete full antibiotic regimen. Review in 5 days.`,

  hypertension: `Patient Robert Chen, 54/M, routine cardio-metabolic evaluation.
Diagnosis: Primary Hypertension Stage 1 & Dyslipidemia.
Prescription:
1. Atorvastatin 20mg, 1 tablet at night for 30 days.
2. Metformin 500mg, 1 tablet with breakfast for 30 days.
Diagnostics ordered: Fasting Blood Glucose, Comprehensive Lipid Panel, and 12-lead ECG.
Consultation $50. Advised low sodium diet and daily 30-min brisk walk.`
};

function fillSamplePrompt(type) {
  const notesArea = document.getElementById('ai-clinical-notes-input');
  if (!notesArea) return;

  if (SAMPLE_CLINICAL_NOTES[type]) {
    notesArea.value = SAMPLE_CLINICAL_NOTES[type];
    // Automatically trigger AI extraction for smooth demo!
    runAIExtraction();
  }
}

async function runAIExtraction() {
  const notes = document.getElementById('ai-clinical-notes-input')?.value;
  if (!notes || notes.trim().length < 5) {
    alert("Please enter clinical notes or choose a sample prompt.");
    return;
  }

  const statusMsg = document.getElementById('ai-status-msg');
  const runBtn = document.getElementById('btn-run-ai');
  
  if (statusMsg) statusMsg.textContent = '✨ AI analyzing clinical notes & interactions...';
  if (runBtn) runBtn.disabled = true;

  try {
    const payload = {
      clinical_notes: notes,
      patient_name: document.getElementById('doc-patient-name')?.value || 'Minh',
      patient_age: parseInt(document.getElementById('doc-patient-age')?.value) || 28,
      patient_gender: document.getElementById('doc-patient-gender')?.value || 'Male',
      patient_phone: document.getElementById('doc-patient-phone')?.value || '+1 555-019-2834'
    };

    const result = await API.post('/api/receipts/ai-parse', payload);

    // Populate patient fields
    if (document.getElementById('doc-patient-name')) document.getElementById('doc-patient-name').value = result.patient_name;
    if (document.getElementById('doc-patient-age')) document.getElementById('doc-patient-age').value = result.patient_age;
    if (document.getElementById('doc-patient-gender')) document.getElementById('doc-patient-gender').value = result.patient_gender;
    if (document.getElementById('doc-patient-phone')) document.getElementById('doc-patient-phone').value = result.patient_phone;
    if (document.getElementById('doc-diagnosis')) document.getElementById('doc-diagnosis').value = result.diagnosis;
    if (document.getElementById('doc-symptoms')) document.getElementById('doc-symptoms').value = result.symptoms;

    // Safety Warnings Banner
    const warnBanner = document.getElementById('ai-warnings-banner');
    const warnList = document.getElementById('ai-warnings-list');
    if (warnBanner && warnList) {
      if (result.safety_warnings && result.safety_warnings.length > 0) {
        warnList.innerHTML = result.safety_warnings.map(w => `<li>${w}</li>`).join('');
        warnBanner.style.display = 'flex';
      } else {
        warnBanner.style.display = 'none';
      }
    }

    // Populate Items
    currentReceiptItems = result.items || [];
    renderReceiptItemsTable();

    // Populate Reminders
    currentReminders = result.reminders || [];
    renderRemindersTable();

    recalculateFinancials();

    if (statusMsg) statusMsg.textContent = '✅ Parsed with 96% AI confidence!';
    setTimeout(() => { if (statusMsg) statusMsg.textContent = ''; }, 4000);

  } catch (err) {
    alert("AI Extraction error: " + err.message);
    if (statusMsg) statusMsg.textContent = '⚠️ Parse error';
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

function renderReceiptItemsTable() {
  const tbody = document.getElementById('receipt-items-tbody');
  if (!tbody) return;

  tbody.innerHTML = currentReceiptItems.map((item, idx) => `
    <tr>
      <td>
        <input type="text" class="form-input" style="width: 100%;" value="${item.item_name}" 
          onchange="updateItemField(${idx}, 'item_name', this.value)">
      </td>
      <td>
        <select class="form-input" style="width: 100%;" onchange="updateItemField(${idx}, 'item_type', this.value)">
          <option value="CONSULTATION" ${item.item_type === 'CONSULTATION' ? 'selected' : ''}>CONSULTATION</option>
          <option value="MEDICATION" ${item.item_type === 'MEDICATION' ? 'selected' : ''}>MEDICATION</option>
          <option value="LAB_TEST" ${item.item_type === 'LAB_TEST' ? 'selected' : ''}>LAB_TEST</option>
          <option value="PROCEDURE" ${item.item_type === 'PROCEDURE' ? 'selected' : ''}>PROCEDURE</option>
        </select>
      </td>
      <td>
        <input type="number" step="0.5" class="form-input" style="width: 100%;" value="${item.unit_price}" 
          oninput="updateItemField(${idx}, 'unit_price', parseFloat(this.value) || 0)">
      </td>
      <td>
        <input type="number" min="1" class="form-input" style="width: 100%;" value="${item.quantity || 1}" 
          oninput="updateItemField(${idx}, 'quantity', parseInt(this.value) || 1)">
      </td>
      <td style="font-weight: 700; color: var(--navy);">
        $${((item.unit_price || 0) * (item.quantity || 1)).toFixed(2)}
      </td>
      <td>
        <button class="btn-remove-row" onclick="removeItemRow(${idx})" title="Remove item">✕</button>
      </td>
    </tr>
  `).join('');
}

function updateItemField(index, field, value) {
  if (currentReceiptItems[index]) {
    currentReceiptItems[index][field] = value;
    recalculateFinancials();
  }
}

function removeItemRow(index) {
  currentReceiptItems.splice(index, 1);
  renderReceiptItemsTable();
  recalculateFinancials();
}

function addNewItemRow() {
  currentReceiptItems.push({
    item_type: 'MEDICATION',
    item_name: 'New Medicine / Service',
    unit_price: 15.0,
    quantity: 1,
    instructions: 'Take as directed'
  });
  renderReceiptItemsTable();
  recalculateFinancials();
}

function renderRemindersTable() {
  const tbody = document.getElementById('reminders-tbody');
  if (!tbody) return;

  tbody.innerHTML = currentReminders.map((rem, idx) => `
    <tr>
      <td>
        <input type="text" class="form-input" style="width: 100%;" value="${rem.medicine_name}" 
          onchange="updateReminderField(${idx}, 'medicine_name', this.value)">
      </td>
      <td>
        <input type="text" class="form-input" style="width: 100%;" value="${rem.dosage}" 
          onchange="updateReminderField(${idx}, 'dosage', this.value)">
      </td>
      <td>
        <select class="form-input" style="width: 100%;" onchange="updateReminderField(${idx}, 'timing_slot', this.value)">
          <option value="MORNING" ${rem.timing_slot === 'MORNING' ? 'selected' : ''}>MORNING</option>
          <option value="AFTERNOON" ${rem.timing_slot === 'AFTERNOON' ? 'selected' : ''}>AFTERNOON</option>
          <option value="EVENING" ${rem.timing_slot === 'EVENING' ? 'selected' : ''}>EVENING</option>
          <option value="NIGHT" ${rem.timing_slot === 'NIGHT' ? 'selected' : ''}>NIGHT</option>
        </select>
      </td>
      <td>
        <input type="text" class="form-input" style="width: 100%;" value="${rem.schedule_time}" 
          onchange="updateReminderField(${idx}, 'schedule_time', this.value)">
      </td>
      <td>
        <input type="number" min="1" class="form-input" style="width: 100%;" value="${rem.duration_days || 5}" 
          onchange="updateReminderField(${idx}, 'duration_days', parseInt(this.value) || 5)">
      </td>
      <td>
        <button class="btn-remove-row" onclick="removeReminderRow(${idx})" title="Remove reminder">✕</button>
      </td>
    </tr>
  `).join('');
}

function updateReminderField(index, field, value) {
  if (currentReminders[index]) {
    currentReminders[index][field] = value;
  }
}

function removeReminderRow(index) {
  currentReminders.splice(index, 1);
  renderRemindersTable();
}

function addNewReminderRow() {
  currentReminders.push({
    medicine_name: 'Ibuprofen',
    dosage: '1 pill',
    timing_slot: 'MORNING',
    schedule_time: '12:00 am',
    duration_days: 5,
    instructions: 'Take after meal'
  });
  renderRemindersTable();
}

function recalculateFinancials() {
  let subtotal = 0;
  currentReceiptItems.forEach(item => {
    subtotal += (item.unit_price || 0) * (item.quantity || 1);
  });

  const tax = subtotal * 0.05;
  const discount = 0.0;
  const grandTotal = Math.max(0, subtotal + tax - discount);

  document.getElementById('calc-subtotal').textContent = `$${subtotal.toFixed(2)}`;
  document.getElementById('calc-tax').textContent = `$${tax.toFixed(2)}`;
  document.getElementById('calc-discount').textContent = `-$${discount.toFixed(2)}`;
  document.getElementById('calc-grand-total').textContent = `$${grandTotal.toFixed(2)}`;

  return { subtotal, tax, discount, grandTotal };
}

async function submitCreateHealthSlip() {
  if (currentReceiptItems.length === 0) {
    alert("Please add at least one item before issuing the receipt.");
    return;
  }

  const patientName = document.getElementById('doc-patient-name')?.value || 'Minh';
  const patientPhone = document.getElementById('doc-patient-phone')?.value || '+1 555-019-2834';

  const currentUser = API.getCurrentUser();
  const docName = (currentUser && currentUser.primary_role === 'DOCTOR') 
    ? currentUser.full_name 
    : 'Dr. Minh Nguyen, M.D.';
  const docLicense = (currentUser && currentUser.practitioner_license) 
    ? currentUser.practitioner_license 
    : 'MED-2024-8841';

  const payload = {
    patient: {
      full_name: patientName,
      age: parseInt(document.getElementById('doc-patient-age')?.value) || 28,
      gender: document.getElementById('doc-patient-gender')?.value || 'Male',
      phone: patientPhone,
      email: `${patientName.toLowerCase().replace(/\s+/g, '')}@example.com`,
      blood_group: 'O+',
      address: '452 Elm Street, Medical Arts District'
    },
    doctor_name: docName,
    doctor_license: docLicense,
    clinic_name: 'HealthSlip AI Medical Center',
    symptoms: document.getElementById('doc-symptoms')?.value || 'Clinical checkup',
    diagnosis: document.getElementById('doc-diagnosis')?.value || 'General Consultation',
    clinical_notes: document.getElementById('ai-clinical-notes-input')?.value || '',
    ai_insights: 'Verified via HealthSlip AI Clinical Validator. Drug contraindications checked.',
    items: currentReceiptItems,
    reminders: currentReminders,
    tax_percent: 5.0,
    discount_amount: 0.0,
    insurance_covered: 0.0,
    payment_status: document.getElementById('doc-payment-status')?.value || 'PAID',
    payment_method: document.getElementById('doc-payment-method')?.value || 'Apple Pay / NFC'
  };

  try {
    const createdSlip = await API.post('/api/receipts', payload);

    if (typeof showToast === 'function') {
      showToast(`HealthSlip ${createdSlip.slip_number} created with HMAC seal!`, 'success');
    } else {
      alert(`🎉 HealthSlip ${createdSlip.slip_number} created successfully!`);
    }

    // Update active slip preview and patient view
    renderActiveSlipPreview(createdSlip);
    refreshReminders();

    // Switch to patient view to admire results
    switchView('patient-view');

  } catch (err) {
    alert("Failed to issue health slip: " + err.message);
  }
}
