// ============================================================================
// Tawashir — demo auth (hackathon prototype only, no real backend)
// A hardcoded credential pair lets judges walk through login -> dashboard
// without needing the API team's auth service wired up yet.
// ============================================================================

const DEMO_NAME = 'Mohammed Abdul Rahman Ali';
const DEMO_EMAIL = 'demo@tawashir.io';
const DEMO_PASSWORD = 'Tawashir@2026';

function setSession(name, email) {
  sessionStorage.setItem('tawashir_auth', 'true');
  sessionStorage.setItem('tawashir_name', name || 'Demo user');
  sessionStorage.setItem('tawashir_email', email);
}

function clearSession() {
  sessionStorage.removeItem('tawashir_auth');
  sessionStorage.removeItem('tawashir_name');
  sessionStorage.removeItem('tawashir_email');
}

function isAuthed() {
  return sessionStorage.getItem('tawashir_auth') === 'true';
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.add('visible');
}

/* ---------------------------------------------------------------------- */
/* Login page                                                              */
/* ---------------------------------------------------------------------- */
function initLoginForm() {
  const form = document.getElementById('login-form');
  if (!form) return;

  const errorEl = document.getElementById('login-error');
  const fillBtn = document.getElementById('demo-fill');

  if (fillBtn) {
    fillBtn.addEventListener('click', () => {
      document.getElementById('login-email').value = DEMO_EMAIL;
      document.getElementById('login-password').value = DEMO_PASSWORD;
    });
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    if (email === DEMO_EMAIL && password === DEMO_PASSWORD) {
      setSession(DEMO_NAME, email);
      window.location.href = 'dashboard.html';
    } else {
      showError(errorEl, 'That email or password doesn\u2019t match our demo account. Use the demo credentials below, or try again.');
    }
  });
}

/* ---------------------------------------------------------------------- */
/* Signup page                                                             */
/* ---------------------------------------------------------------------- */
function initSignupForm() {
  const form = document.getElementById('signup-form');
  if (!form) return;

  const errorEl = document.getElementById('signup-error');
  const fillBtn = document.getElementById('signup-demo-fill');

  if (fillBtn) {
    fillBtn.addEventListener('click', () => {
      document.getElementById('signup-name').value = DEMO_NAME;
      document.getElementById('signup-email').value = DEMO_EMAIL;
      document.getElementById('signup-password').value = DEMO_PASSWORD;
      document.getElementById('signup-confirm').value = DEMO_PASSWORD;
      errorEl.classList.remove('visible');
    });
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const name = document.getElementById('signup-name').value.trim();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;
    const confirm = document.getElementById('signup-confirm').value;

    if (!name) return showError(errorEl, 'Enter your name the way you use it.');
    if (!email || !password) return showError(errorEl, 'Enter an email and password to continue.');
    if (password !== confirm) return showError(errorEl, 'Passwords don\u2019t match.');

    // Demo mode: account creation is simulated locally, then routed to the
    // dashboard. Account creation alone does not mark identity as verified (FR-01).
    setSession(name, email);
    window.location.href = 'dashboard.html';
  });
}

/* ---------------------------------------------------------------------- */
/* Dashboard guard + sign out                                              */
/* ---------------------------------------------------------------------- */
function initDashboardAuth() {
  const shell = document.getElementById('dash-shell');
  if (!shell) return;

  if (!isAuthed()) {
    window.location.href = 'login.html';
    return;
  }

  const fullName = sessionStorage.getItem('tawashir_name') || 'Demo user';
  const nameEl = document.getElementById('dash-username');
  if (nameEl) nameEl.textContent = fullName.split(' ')[0];
  document.querySelectorAll('[data-fullname]').forEach((el) => (el.textContent = fullName.toUpperCase()));

  document.querySelectorAll('[data-signout]').forEach((btn) => {
    btn.addEventListener('click', () => {
      clearSession();
      window.location.href = 'index.html';
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initLoginForm();
  initSignupForm();
  initDashboardAuth();
});