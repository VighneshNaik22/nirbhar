const api = {
  async get(path) {
    const response = await fetch(path);
    return response.json();
  },
  async post(path, payload) {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return response.json();
  },
};

const state = { incidents: [], selectedIncidentId: null };

function badgeClass(confidence) {
  if (confidence === 'Confirmed') return 'confirmed';
  if (confidence === 'Sensor-only') return 'sensor';
  if (confidence === 'Single unverified report') return 'single';
  return 'normal';
}

async function refreshEvidence() {
  const evidence = await api.get('/api/audit');
  const feed = document.getElementById('evidenceFeed');
  feed.innerHTML = evidence.slice(-8).reverse().map(item => `
    <div class="evidence-item">
      <strong>${item.event_type}</strong>
      <div>${item.actor}</div>
      <small>${item.ts}</small>
    </div>
  `).join('') || '<p>No events yet.</p>';
}

async function refreshIncidents() {
  const incidents = await api.get('/api/incidents');
  state.incidents = incidents;
  if (!state.selectedIncidentId && incidents.length) state.selectedIncidentId = incidents[0].id;

  const list = document.getElementById('incidentList');
  list.innerHTML = incidents.map(item => `
    <div class="incident-item" data-id="${item.id}">
      <strong>${item.zone}</strong>
      <span class="badge ${badgeClass(item.confidence)}">${item.confidence}</span>
      <div>${item.reason}</div>
    </div>
  `).join('') || '<p>No incidents.</p>';

  list.querySelectorAll('.incident-item').forEach(card => {
    card.addEventListener('click', () => {
      state.selectedIncidentId = card.dataset.id;
      renderIncidentDetail();
    });
  });

  renderIncidentDetail();
}

async function renderIncidentDetail() {
  const incident = state.incidents.find(item => item.id === state.selectedIncidentId) || state.incidents[0];
  const detail = document.getElementById('incidentDetail');
  if (!incident) {
    detail.innerHTML = '<p>No incident selected.</p>';
    return;
  }
  const payload = await api.get(`/api/incidents/${incident.id}`);
  const recommendation = payload.recommendation || {};
  const steps = (recommendation.steps || []).map(step => `<li>${step}</li>`).join('');
  const missing = (recommendation.missing_evidence || []).map(item => `<li>${item}</li>`).join('');
  detail.innerHTML = `
    <h3>${payload.incident.zone}</h3>
    <p><strong>Confidence:</strong> <span class="badge ${badgeClass(payload.incident.confidence)}">${payload.incident.confidence}</span></p>
    <p><strong>Reason:</strong> ${payload.incident.reason}</p>
    <p><strong>Category:</strong> ${payload.incident.category}</p>
    <div class="recommendation-box">
      <h4>Recommendation</h4>
      <p>${recommendation.message || 'Recommended action based on retrieved SOP content.'}</p>
      <ul>${steps || '<li>Review Required - no matching SOP found</li>'}</ul>
      <p><strong>Missing evidence:</strong></p>
      <ul>${missing || '<li>Missing: no corroborating evidence</li>'}</ul>
    </div>
  `;
}

async function refreshAudit() {
  const entries = await api.get('/api/audit');
  const trail = document.getElementById('auditTrail');
  trail.innerHTML = entries.slice(-6).reverse().map(item => `
    <div class="audit-item">
      <strong>${item.event_type}</strong>
      <div>${item.actor}</div>
      <small>${item.ts}</small>
    </div>
  `).join('') || '<p>No audit entries.</p>';
}

async function loadDemo() {
  await api.post('/api/demo/load', {});
  refreshIncidents();
  refreshEvidence();
  refreshAudit();
}

async function resetDemo() {
  await api.post('/api/demo/reset', {});
  refreshIncidents();
  refreshEvidence();
  refreshAudit();
}

document.getElementById('loadDemo').addEventListener('click', loadDemo);
document.getElementById('resetDemo').addEventListener('click', resetDemo);
document.getElementById('verifyAudit').addEventListener('click', async () => {
  const result = await api.get('/api/audit/verify');
  alert(result.status === 'intact' ? 'Audit intact' : 'Audit tampered');
});

document.querySelectorAll('[data-action]').forEach(button => {
  button.addEventListener('click', async () => {
    const action = button.dataset.action;
    const reason = document.getElementById('approvalReason').value || 'No reason provided';
    const incident = state.incidents[0];
    if (!incident) return;
    const route = `/api/incidents/${incident.id}/${action}`;
    const result = await api.post(route, { reason });
    alert(`${action}: ${result.status || result.message || 'done'}`);
    refreshAudit();
  });
});

(async function init() {
  document.getElementById('activePack').textContent = 'campus';
  await refreshIncidents();
  await refreshEvidence();
  await refreshAudit();
})();
