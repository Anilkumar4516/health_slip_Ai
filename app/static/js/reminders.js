// HealthSlip AI - Medication Reminders & Calendar Manager

let cachedReminders = [];

function initCalendarRibbon() {
  const container = document.getElementById('calendar-days-container');
  const headerTitle = document.getElementById('calendar-header-title');
  if (!container) return;

  const now = new Date();

  // Set real-time current month & year (e.g., "October 2026")
  if (headerTitle) {
    headerTitle.textContent = now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  // Calculate the 7 days of the current week (Sunday to Saturday)
  const currentDayOfWeek = now.getDay(); // 0 is Sunday, 1 is Monday, etc.
  const sunday = new Date(now);
  sunday.setDate(now.getDate() - currentDayOfWeek);

  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const daysData = [];

  for (let i = 0; i < 7; i++) {
    const d = new Date(sunday);
    d.setDate(sunday.getDate() + i);
    const isToday = d.toDateString() === now.toDateString();
    daysData.push({
      name: dayNames[i],
      num: d.getDate(),
      active: isToday
    });
  }

  container.innerHTML = daysData.map(d => `
    <button class="cal-day-pill ${d.active ? 'active' : ''}" onclick="selectCalendarDay(this, ${d.num})">
      <span class="cal-day-name">${d.name}</span>
      <span class="cal-day-num">${d.num}</span>
    </button>
  `).join('');
}

function selectCalendarDay(btn, num) {
  document.querySelectorAll('.cal-day-pill').forEach(el => el.classList.remove('active'));
  btn.classList.add('active');
}

async function refreshReminders() {
  try {
    const reminders = await API.get('/api/reminders');
    cachedReminders = reminders;
    renderReminders(cachedReminders);
  } catch (err) {
    console.error("Failed to load reminders:", err);
  }
}

function renderReminders(remindersList) {
  const morningContainer = document.getElementById('slot-morning-items');
  const afternoonContainer = document.getElementById('slot-afternoon-items');
  const eveningContainer = document.getElementById('slot-evening-items');

  if (!morningContainer || !afternoonContainer || !eveningContainer) return;

  morningContainer.innerHTML = '';
  afternoonContainer.innerHTML = '';
  eveningContainer.innerHTML = '';

  let doneCount = 0;

  remindersList.forEach(rem => {
    if (rem.is_done) doneCount++;

    const cardHtml = createReminderCardHtml(rem);
    const slot = (rem.timing_slot || '').toUpperCase();
    const timeStr = (rem.schedule_time || '').toLowerCase();

    if (slot === 'MORNING' || timeStr.includes('am') || timeStr.includes('12:00')) {
      morningContainer.insertAdjacentHTML('beforeend', cardHtml);
    } else if (slot === 'AFTERNOON' || timeStr.includes('lunch') || timeStr.includes('afternoon')) {
      afternoonContainer.insertAdjacentHTML('beforeend', cardHtml);
    } else {
      eveningContainer.insertAdjacentHTML('beforeend', cardHtml);
    }
  });

  // If a slot is empty, show a gentle note or default
  if (!morningContainer.hasChildNodes()) {
    morningContainer.innerHTML = `<div style="font-size: 0.78rem; color: var(--text-dim); padding: 0.35rem 0;">No morning doses scheduled.</div>`;
  }
  if (!afternoonContainer.hasChildNodes()) {
    afternoonContainer.innerHTML = `<div style="font-size: 0.78rem; color: var(--text-dim); padding: 0.35rem 0;">No afternoon doses scheduled.</div>`;
  }
  if (!eveningContainer.hasChildNodes()) {
    eveningContainer.innerHTML = `<div style="font-size: 0.78rem; color: var(--text-dim); padding: 0.35rem 0;">No evening doses scheduled.</div>`;
  }

  // Update Adherence Indicator
  const total = remindersList.length;
  const pct = total > 0 ? Math.round((doneCount / total) * 100) : 100;
  const badge = document.getElementById('adherence-badge');
  if (badge) {
    badge.textContent = `${pct}% Adherence`;
    badge.style.color = pct >= 80 ? 'var(--emerald-text)' : 'var(--amber-dark)';
    badge.style.background = pct >= 80 ? 'var(--emerald-light)' : 'var(--amber-light)';
  }
}

function createReminderCardHtml(rem) {
  // Parse schedule time for nice presentation
  const isDone = rem.is_done;
  const timeText = rem.schedule_time || '12:00 am';

  return `
    <div class="reminder-card" id="rem-card-${rem.id}">
      <div class="reminder-time-col">
        <span class="rem-time-val">${timeText}</span>
      </div>
      <div class="reminder-info-col">
        <div class="rem-med-title">${rem.medicine_name}</div>
        <div class="pill-dosage-tag">${rem.dosage}</div>
        <div class="rem-instructions">${rem.instructions || 'Take with water'}</div>
      </div>
      <button 
        class="reminder-action-btn ${isDone ? 'is-done' : 'is-pending'}" 
        onclick="toggleReminderDone(${rem.id})"
        title="Click to toggle taken status">
        ${isDone ? 'DONE' : 'DONE'}
      </button>
    </div>
  `;
}

async function toggleReminderDone(reminderId) {
  try {
    const updated = await API.post(`/api/reminders/${reminderId}/toggle`, {});
    
    // Update local cache and re-render
    const idx = cachedReminders.findIndex(r => r.id === reminderId);
    if (idx !== -1) {
      cachedReminders[idx] = updated;
      renderReminders(cachedReminders);
    } else {
      refreshReminders();
    }
  } catch (err) {
    alert("Could not update reminder status: " + err.message);
  }
}

function filterReminders() {
  const query = (document.getElementById('phone-search-input')?.value || '').toLowerCase();
  if (!query) {
    renderReminders(cachedReminders);
    return;
  }

  const filtered = cachedReminders.filter(r => 
    r.medicine_name.toLowerCase().includes(query) ||
    r.dosage.toLowerCase().includes(query) ||
    (r.instructions || '').toLowerCase().includes(query) ||
    (r.schedule_time || '').toLowerCase().includes(query)
  );

  renderReminders(filtered);
}
