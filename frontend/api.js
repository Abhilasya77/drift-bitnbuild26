// ============================================================================
// Tawashir — API client for the FastAPI backend.
// Local:    backend on http://127.0.0.1:8001 (uvicorn app.main:app --reload --port 8001)
// Deployed: Render URL below. Override any time with ?api=https://... in the URL.
// Login: the backend runs in demo auth mode, so the signed-in email is sent as X-Demo-User.
// ============================================================================
const RENDER_API = 'https://drift-backend-oemw.onrender.com';

const API_BASE = (() => {
  try {
    const fromUrl = new URLSearchParams(location.search).get('api');
    if (fromUrl) localStorage.setItem('tawashir_api', fromUrl);
    const saved = localStorage.getItem('tawashir_api');
    if (saved) return saved.replace(/\/$/, '');
  } catch (e) { /* storage blocked: use defaults */ }
  const local = ['localhost', '127.0.0.1', ''].includes(location.hostname);
  return local ? 'http://127.0.0.1:8001' : RENDER_API;
})();

function currentEmail() {
  return sessionStorage.getItem('tawashir_email') || 'demo@tawashir.io';
}

function authHeaders(email) {
  return { 'X-Demo-User': email || currentEmail() };
}

async function api(path, { method = 'GET', body, form, as, email } = {}) {
  const headers = authHeaders(email);
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method, headers,
      body: form || (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch (e) {
    throw new Error('Cannot reach the server. If it was idle, it may take up to a minute to wake up. Try again.');
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const err = await res.json();
      const d = err.detail;
      if (typeof d === 'string') msg = d;
      else if (d && d.message) msg = d.message + (d.missing ? ' Missing: ' + d.missing.join(', ') + '.' : '');
      else if (Array.isArray(d)) msg = d.map((x) => x.msg).join('; ');
    } catch (e) { /* not JSON */ }
    const error = new Error(msg);
    error.status = res.status;
    throw error;
  }
  if (as === 'blob') return res.blob();
  return res.status === 204 ? null : res.json();
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  return isNaN(d) ? esc(value) : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

const CLASS_CHIP = {
  match: ['lchip--match', 'Match'],
  explainable_variant: ['lchip--variant', 'Explainable variant'],
  uncertain: ['lchip--uncertain', 'Uncertain'],
  conflict: ['lchip--conflict', 'Conflict'],
};

function classChip(c) {
  const [cls, label] = CLASS_CHIP[c] || ['lchip--neutral', (c || '').replace(/_/g, ' ')];
  return `<span class="lchip ${cls}">${esc(label)}</span>`;
}

function statusChip(text, tone = 'neutral') {
  return `<span class="chip ${tone}">${esc(text)}</span>`;
}

const DOC_LABEL = {
  passport: 'Passport', national_id: 'National ID', gcc_id: 'GCC ID', visa_residence: 'Visa / residence',
  grade10: 'Grade 10 certificate', grade12: 'Grade 12 certificate', other: 'Other document',
};
