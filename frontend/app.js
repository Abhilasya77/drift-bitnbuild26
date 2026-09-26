// ============================================================================
// Tawashir — live app (talks to the FastAPI backend through api.js)
// Sections: overview, identity, documents, consistency, biometric, credential, health, notifications
// ============================================================================
const main = document.getElementById('app-main');
const state = { me: null, docs: [], cred: null, qrUrl: null };
let camStream = null;

const SAMPLES = [
  { label: 'Ravi · passport', type: 'passport', file: 'demo-docs/ravi_passport.png' },
  { label: 'Ravi · visa', type: 'visa_residence', file: 'demo-docs/ravi_visa.png' },
  { label: 'Ravi · Grade 10', type: 'grade10', file: 'demo-docs/ravi_grade10.png' },
  { label: 'Ravi · permanent ID', type: 'national_id', file: 'demo-docs/ravi_permanent_id.png', permanent: true },
  { label: 'Priya · passport (edited DOB)', type: 'passport', file: 'demo-docs/priya_passport_tampered.png' },
  { label: 'Priya · visa', type: 'visa_residence', file: 'demo-docs/priya_visa.png' },
];

function showMsg(id, text, tone = 'info') {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `msg ${tone} show`;
  el.textContent = text;
}

async function busy(btn, fn) {
  const old = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Working…'; }
  try { return await fn(); } finally { if (btn) { btn.disabled = false; btn.innerHTML = old; } }
}

function stopCamera() {
  if (camStream) { camStream.getTracks().forEach((t) => t.stop()); camStream = null; }
}

// ---------------------------------------------------------------- routing
const SECTIONS = ['overview', 'identity', 'documents', 'consistency', 'biometric', 'credential', 'health', 'notifications'];

async function route() {
  const name = SECTIONS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === name));
  stopCamera();
  main.innerHTML = '<p class="msg info show">Loading…</p>';
  try {
    await loadMe();
    if (!state.me && name !== 'identity') {
      renderStart();
      return;
    }
    await RENDER[name]();
  } catch (e) {
    main.innerHTML = `<div class="dash-head"><div><h1>Something went wrong</h1><p class="sub">${esc(e.message)}</p></div></div>
      <div class="btn-row"><button class="btn" onclick="route()">Try again</button></div>
      <p class="dim" style="margin-top:14px">API: ${esc(API_BASE)}</p>`;
  }
}

async function loadMe() {
  try {
    state.me = await api('/profiles/me');
    const badge = document.getElementById('nav-badge');
    if (badge) {
      badge.textContent = state.me.unread_notifications;
      badge.style.display = state.me.unread_notifications ? '' : 'none';
    }
  } catch (e) {
    if (e.status === 404) state.me = null; else throw e;
  }
}

function toHash(route) {
  const parts = String(route || '').split('/').filter(Boolean);   // e.g. /app/documents/<id> -> documents
  return SECTIONS.includes(parts[1]) ? parts[1] : 'overview';
}

function head(title, sub) {
  return `<div class="dash-head anim" style="--d:.02s"><div><h1>${title}</h1><p class="sub">${sub}</p></div></div>`;
}

function renderStart() {
  const name = sessionStorage.getItem('tawashir_name') || 'there';
  main.innerHTML = head(`Welcome, ${esc(name.split(' ')[0])}`, 'Account created. Your identity is not verified yet.') + `
    <section class="dash-hero anim" style="--d:.1s"><div>
      <p class="hero-label">Identity continuity</p><h2>Identity setup not completed</h2>
      <p class="hero-desc">Start by telling us your name the way you use it. Then add your documents: we'll link every version of your name into one identity.</p>
      <div class="btn-row"><a class="btn" href="#identity">Start identity setup</a></div>
    </div></section>`;
}

// ---------------------------------------------------------------- overview
async function renderOverview() {
  const me = state.me;
  const s = me.status;
  const [elig, notes] = await Promise.all([api('/eligibility'), api('/notifications')]);
  let cred = null;
  try { cred = await api('/credentials/current'); } catch (e) { /* none yet */ }

  const heroTitle = {
    evidence_backed: 'Evidence backed', under_review: 'Under review', action_required: 'Action required',
    self_declared: 'Self-declared',
  }[me.profile.evidence_status] || me.profile.evidence_status;

  const chips = [
    s.documents ? `<span class="lchip lchip--match">${s.documents} documents</span>` : '',
    s.consistency !== 'not_run' ? classChip(s.consistency) : '',
    s.biometric === 'passed' ? '<span class="lchip lchip--match">Biometric passed</span>' : '',
  ].join(' ');

  main.innerHTML = head(`Welcome back, ${esc(me.profile.name_as_used.split(' ')[0])}`, "Here's where your identity stands today.") + `
    <section class="dash-hero anim" style="--d:.1s">
      <div>
        <p class="hero-label">Identity continuity</p>
        <h2>${esc(heroTitle)}</h2>
        <p class="hero-desc">Next step: <strong>${esc(me.next_action.label)}</strong></p>
        <div class="hero-chips">${chips}</div>
        <div class="btn-row"><a class="btn" href="#${toHash(me.next_action.route)}">${esc(me.next_action.label)}</a></div>
      </div>
      ${cred ? `<div class="mini-cred">
        <div class="cred-top"><span class="cred-brand" style="font-size:14px">Temporary credential</span><span class="status-dot">${esc(cred.state)}</span></div>
        <div class="cred-mid"><div>
          <p class="cred-name" style="font-size:13px">${esc(me.profile.name_as_used.toUpperCase())}</p>
          <p class="cred-id">${esc(cred.public_credential_id)}</p>
          <div class="cred-meta" style="margin-top:12px"><p><small>Expires</small>${fmtDate(cred.expires_at)}</p></div>
        </div><img id="mini-qr" alt="Credential QR" style="width:78px;height:78px;border-radius:10px;background:#fff;padding:4px"></div>
      </div>` : ''}
    </section>
    <div class="dash-grid">
      ${card('fa-code-compare', 'Identity consistency', (s.consistency || 'not run').replace(/_/g, ' '),
        s.review !== 'none' ? 'A reviewer is checking one detail.' : 'Differences are explained automatically.',
        s.consistency === 'match' || s.consistency === 'explainable_variant' ? ['Passed', 'positive'] :
          s.consistency === 'not_run' ? ['Not run', 'neutral'] : ['Review', 'warn'])}
      ${card('fa-fingerprint', 'Biometric verification', s.biometric.replace(/_/g, ' '), 'Prototype face verification step.',
        s.biometric === 'passed' ? ['Passed', 'positive'] : ['Pending', 'neutral'])}
      ${card('fa-regular fa-id-card', 'Permanent credential', s.permanent_credential.replace(/_/g, ' '),
        'Upload it when it arrives: we link it and retire the temporary credential.',
        s.permanent_credential === 'linked' ? ['Linked', 'positive'] : ['Pending', 'neutral'])}
      ${card('fa-regular fa-calendar', 'Document health', healthLine(me.document_health), 'Reminders 30 and 7 days before expiry.',
        me.document_health.some((d) => d.days_left !== null && d.days_left <= 60) ? ['Renews soon', 'warn'] : ['OK', 'positive'])}
    </div>
    <div class="dash-split">
      <div class="panel anim" style="--d:.34s"><h3>Credential requirements</h3>
        <ul class="checklist">${elig.items.map((i) => `<li><span class="tick ${i.passed ? 'done' : 'todo'}">
          <i class="fa-solid ${i.passed ? 'fa-check' : 'fa-hourglass-half'}"></i></span>${esc(i.label)}
          ${statusChip(i.status, i.passed ? 'positive' : 'neutral')}</li>`).join('')}</ul>
      </div>
      <div class="panel anim" style="--d:.38s"><h3>Notifications</h3>
        ${notes.slice(0, 3).map(noticeHtml).join('') || '<p class="muted">No notifications yet.</p>'}
      </div>
    </div>`;
  if (cred) loadQr('mini-qr');
}

function card(icon, label, value, note, [chip, tone]) {
  const i = icon.startsWith('fa-regular') ? icon : `fa-solid ${icon}`;
  return `<div class="dash-card anim"><div class="card-top"><span class="card-icon"><i class="${i}"></i></span>
    ${statusChip(chip, tone)}</div><p class="label">${esc(label)}</p><p class="value" style="text-transform:capitalize">${esc(value)}</p>
    <p class="note">${esc(note)}</p></div>`;
}

function healthLine(items) {
  const soon = items.filter((d) => d.days_left !== null).sort((a, b) => a.days_left - b.days_left)[0];
  if (!soon) return 'No expiry dates yet';
  return `${DOC_LABEL[soon.document_type] || soon.document_type}: ${soon.days_left} days left`;
}

function noticeHtml(n) {
  return `<div class="notice ${n.read ? 'soft' : ''}"><i class="fa-regular fa-bell"></i><div>
    <strong>${esc(n.title)}</strong><p>${esc(n.message)}</p>
    ${n.action_route ? `<a href="#${toHash(n.action_route)}">Open</a>` : ''}</div></div>`;
}

async function loadQr(imgId) {
  const img = document.getElementById(imgId);
  if (!img) return;
  try {
    const blob = await api('/credentials/current/qr', { as: 'blob' });
    if (state.qrUrl) URL.revokeObjectURL(state.qrUrl);
    state.qrUrl = URL.createObjectURL(blob);
    img.src = state.qrUrl;
  } catch (e) { /* no QR yet */ }
}

// ---------------------------------------------------------------- identity
async function renderIdentity() {
  const p = state.me ? state.me.profile : {};
  const name = p.name_as_used || sessionStorage.getItem('tawashir_name') || '';
  const f = (id, label, value, type = 'text', hint = '') => `<div class="field"><label for="${id}">${label}</label>
    <input id="${id}" type="${type}" value="${esc(value || '')}" />${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
  main.innerHTML = head('Identity profile', state.me ? `Status: ${esc(p.evidence_status.replace(/_/g, ' '))}` :
    'Self-declared until you add documents.') + `
    <div class="panel anim"><h3>Your details</h3>
      <div class="form-grid">
        ${f('p-name', 'Name as you use it', name, 'text', 'One box, any script, any number of names. No first/last split.')}
        ${f('p-dob', 'Date of birth', p.date_of_birth, 'date')}
        ${f('p-nat', 'Nationality', p.nationality || 'India')}
        ${f('p-country', 'Current country', p.current_country || 'United Arab Emirates')}
        ${f('p-phone', 'Phone (with country code)', p.phone_number || '+971', 'tel')}
        ${f('p-father', "Father's name (optional)", p.father_name, 'text', 'Helps explain documents that add your father’s name.')}
        ${f('p-mother', "Mother's name (optional)", p.mother_name)}
      </div>
      <div class="btn-row"><button class="btn" id="save-profile">${state.me ? 'Save changes' : 'Save & continue'}</button>
        <button class="btn ghost" id="fill-ravi">Fill demo (Ravi)</button></div>
      <p class="msg" id="profile-msg"></p>
    </div>`;
  document.getElementById('fill-ravi').onclick = () => {
    document.getElementById('p-name').value = 'Ravi Kumar Venkatesh';
    document.getElementById('p-dob').value = '1994-03-12';
    document.getElementById('p-nat').value = 'India';
    document.getElementById('p-country').value = 'United Arab Emirates';
    document.getElementById('p-phone').value = '+971501234567';
    document.getElementById('p-father').value = 'Srinivasa Rao';
  };
  document.getElementById('save-profile').onclick = (e) => busy(e.currentTarget, async () => {
    const v = (id) => document.getElementById(id).value.trim();
    const body = {
      name_as_used: v('p-name'), date_of_birth: v('p-dob'), nationality: v('p-nat'), current_country: v('p-country'),
      phone_number: v('p-phone') || null, father_name: v('p-father') || null, mother_name: v('p-mother') || null,
    };
    if (!body.name_as_used || !body.date_of_birth) return showMsg('profile-msg', 'Please enter your name and date of birth.', 'err');
    try {
      if (state.me) await api('/profiles/me', { method: 'PATCH', body });
      else await api('/profiles', { method: 'POST', body });
      sessionStorage.setItem('tawashir_name', body.name_as_used);
      showMsg('profile-msg', 'Saved.', 'ok');
      if (!state.me) setTimeout(() => { location.hash = '#documents'; }, 500);
    } catch (err) { showMsg('profile-msg', err.message, 'err'); }
  });
}

// ---------------------------------------------------------------- documents
async function renderDocuments() {
  state.docs = await api('/documents');
  const rows = state.docs.map((d) => `<tr>
      <td><strong>${esc(DOC_LABEL[d.document_type] || d.document_type)}</strong><br><span class="dim">${esc(d.evidence_class)}${d.is_permanent_credential ? ' · permanent ID' : ''}</span></td>
      <td>${statusChip(d.processing_status.replace(/_/g, ' '), d.processing_status === 'processed' ? 'positive' : 'warn')}
          ${d.renewal_status !== 'current' ? statusChip(d.renewal_status.replace(/_/g, ' '), 'neutral') : ''}</td>
      <td>${d.fields_confirmed ? statusChip('Confirmed', 'positive') : statusChip('Needs check', 'warn')}</td>
      <td>${fmtDate(d.expiry_date)}</td>
      <td><button class="btn small ghost" data-open="${d.id}">${d.fields_confirmed ? 'View' : 'Check fields'}</button>
          ${d.is_permanent_credential && d.fields_confirmed && state.me.status.permanent_credential !== 'linked'
            ? `<button class="btn small" data-link="${d.id}">Link permanent ID</button>` : ''}</td></tr>`).join('');

  main.innerHTML = head('Documents', 'Primary evidence: passport, national/GCC ID, visa. Supporting: school certificates.') + `
    <div class="panel anim"><h3>Add a document</h3>
      <div class="form-grid">
        <div class="field"><label for="d-type">Document type</label><select id="d-type">
          ${Object.entries(DOC_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div>
        <div class="field"><label for="d-file">File (JPG, PNG or PDF, max 5 MB)</label><input id="d-file" type="file" accept="image/jpeg,image/png,application/pdf" /></div>
        <div class="field" style="display:flex;align-items:center"><label style="display:flex;align-items:center;margin:0">
          <input id="d-perm" type="checkbox" />This is my new permanent ID (e.g. Emirates ID)</label></div>
      </div>
      <div class="btn-row"><button class="btn" id="d-upload">Upload & read</button></div>
      <p class="dim" style="margin-top:14px">Or use a synthetic demo document (marked SPECIMEN):</p>
      <div class="samples">${SAMPLES.map((s, i) => `<button class="btn small ghost" data-sample="${i}">${esc(s.label)}</button>`).join('')}</div>
      <p class="msg" id="doc-msg"></p>
    </div>
    <div class="panel anim"><h3>Your documents</h3>
      ${state.docs.length ? `<div class="tbl-wrap"><table class="tbl"><tr><th>Document</th><th>Processing</th><th>Fields</th><th>Expiry</th><th></th></tr>${rows}</table></div>`
        : '<p class="muted">No documents yet.</p>'}
      ${state.docs.length && state.docs.every((d) => d.fields_confirmed) ? '<div class="btn-row"><a class="btn" href="#consistency">Continue to consistency check</a></div>' : ''}
    </div>
    <div id="doc-detail"></div>`;

  document.getElementById('d-upload').onclick = (e) => busy(e.currentTarget, async () => {
    const file = document.getElementById('d-file').files[0];
    if (!file) return showMsg('doc-msg', 'Choose a file first.', 'err');
    await uploadAndRead(document.getElementById('d-type').value, file, document.getElementById('d-perm').checked);
  });
  main.querySelectorAll('[data-sample]').forEach((b) => (b.onclick = () => busy(b, async () => {
    const s = SAMPLES[b.dataset.sample];
    const blob = await (await fetch(s.file)).blob();
    await uploadAndRead(s.type, new File([blob], s.file.split('/').pop(), { type: 'image/png' }), !!s.permanent);
  })));
  main.querySelectorAll('[data-open]').forEach((b) => (b.onclick = () => openDoc(b.dataset.open)));
  main.querySelectorAll('[data-link]').forEach((b) => (b.onclick = () => busy(b, () => linkPermanent(b.dataset.link))));
}

async function uploadAndRead(type, file, permanent) {
  try {
    showMsg('doc-msg', 'Uploading and reading the document…', 'info');
    const form = new FormData();
    form.append('document_type', type);
    form.append('file', file);
    if (permanent) form.append('is_permanent_credential', 'true');
    const doc = await api('/documents', { method: 'POST', form });
    const processed = await api(`/documents/${doc.id}/process`, { method: 'POST' });
    await renderDocuments();
    showMsg('doc-msg', processed.note || 'Read. Please check the fields below.', 'ok');
    openDoc(doc.id, processed);
  } catch (err) { showMsg('doc-msg', err.message, 'err'); }
}

async function openDoc(id, preloaded) {
  const d = preloaded || await api(`/documents/${id}`);
  const val = (name) => (d.fields.find((f) => f.field_name === name) || {}).value || '';
  const mrz = val('mrz_check');
  const f = (key, label, type = 'text', hint = '') => `<div class="field"><label>${label}</label>
    <input data-f="${key}" type="${type}" value="${esc(val(key))}" />${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
  document.getElementById('doc-detail').innerHTML = `<div class="panel anim"><h3>${esc(DOC_LABEL[d.document_type])}: check the details we read</h3>
    ${mrz ? `<p>${mrz === 'passed' ? statusChip('Passport MRZ check digits: passed', 'positive') : statusChip('Passport MRZ check digits: failed', 'conflict')}</p>` : ''}
    <p class="dim">Enter values exactly as printed on this document. Reading is automatic but not authoritative.</p>
    <div class="form-grid">
      ${f('name', 'Name as printed', 'text', 'Keep the exact order and spelling of this document.')}
      ${f('dob', 'Date of birth', 'date')}
      ${f('nationality', 'Nationality')}
      ${f('document_number', 'Document number')}
      ${f('expiry_date', 'Expiry date', 'date')}
      ${f('father_name', "Father's name (if printed)")}
    </div>
    <div class="btn-row"><button class="btn" id="confirm-fields">Confirm fields</button>
      ${d.expiry_date && d.renewal_status === 'current' ? '<button class="btn ghost" id="mark-renewal">Mark renewal in progress</button>' : ''}</div>
    <p class="msg" id="field-msg"></p></div>`;
  document.getElementById('doc-detail').scrollIntoView({ behavior: 'smooth' });
  document.getElementById('confirm-fields').onclick = (e) => busy(e.currentTarget, async () => {
    const body = {};
    document.querySelectorAll('[data-f]').forEach((i) => { if (i.value.trim()) body[i.dataset.f] = i.value.trim(); });
    try {
      await api(`/documents/${d.id}/confirm-fields`, { method: 'POST', body });
      await loadMe();
      await renderDocuments();
      showMsg('doc-msg', `${DOC_LABEL[d.document_type]} confirmed.`, 'ok');
    } catch (err) { showMsg('field-msg', err.message, 'err'); }
  });
  const r = document.getElementById('mark-renewal');
  if (r) r.onclick = () => busy(r, async () => { await api(`/documents/${d.id}/renewal`, { method: 'POST' }); await renderDocuments(); });
}

async function linkPermanent(docId) {
  try {
    const res = await api('/permanent-credential', { method: 'POST', body: { document_id: docId } });
    await loadMe();
    await renderDocuments();
    showMsg('doc-msg', res.outcome === 'linked'
      ? 'Permanent ID linked. Your temporary credential has expired (and is revoked on-chain).'
      : 'Your new ID differs from earlier documents. A reviewer will check; your temporary credential stays usable.',
      res.outcome === 'linked' ? 'ok' : 'info');
  } catch (err) { showMsg('doc-msg', err.message, 'err'); }
}

// ---------------------------------------------------------------- consistency
async function renderConsistency() {
  let report = null;
  try { report = await api('/consistency/latest'); } catch (e) { if (e.status !== 404) throw e; }
  main.innerHTML = head('Consistency report', 'Your profile and documents compared with each other. Only unexplained differences go to a person.') + `
    <div class="panel anim"><div class="btn-row" style="margin-top:0"><button class="btn" id="run-check">${report ? 'Re-run check' : 'Run consistency check'}</button></div>
      <p class="msg" id="cons-msg"></p></div>
    <div id="report">${report ? reportHtml(report) : ''}</div>`;
  document.getElementById('run-check').onclick = (e) => busy(e.currentTarget, async () => {
    try {
      const r = await api('/consistency/evaluate', { method: 'POST' });
      await loadMe();
      document.getElementById('report').innerHTML = reportHtml(r);
      showMsg('cons-msg', r.requires_review ? 'Sent to a reviewer: only the highlighted fields will be checked.' : 'Documentary identity passed.',
        r.requires_review ? 'info' : 'ok');
    } catch (err) { showMsg('cons-msg', err.message, 'err'); }
  });
}

function reportHtml(r) {
  return `<div class="panel anim"><h3>Result: ${classChip(r.overall_status)}</h3><p class="muted">${esc(r.summary)}</p>
    ${r.review ? `<p>${statusChip('Review: ' + r.review.status.replace(/_/g, ' '), 'warn')}</p>` : ''}
    <div class="tbl-wrap"><table class="tbl"><tr><th>Field</th><th>Compared</th><th>Values</th><th>Result</th><th>Why</th></tr>
    ${r.comparisons.map((c) => `<tr><td>${esc(c.field.replace(/_/g, ' '))}</td><td>${esc(c.source_a)} vs ${esc(c.source_b)}</td>
      <td class="dim">${esc(c.value_a)}<br>${esc(c.value_b)}</td><td>${classChip(c.classification)}</td>
      <td class="explain-cell">${esc(c.explanation)}</td></tr>`).join('')}</table></div>
    ${!r.requires_review ? '<div class="btn-row"><a class="btn" href="#biometric">Continue to biometric check</a></div>' : ''}</div>`;
}

// ---------------------------------------------------------------- biometric
async function renderBiometric() {
  const st = await api('/biometric/status');
  main.innerHTML = head('Biometric verification', esc(st.disclaimer)) + `
    <div class="panel anim"><h3>Status: ${statusChip(st.status.replace(/_/g, ' '), st.status === 'passed' ? 'positive' : 'neutral')}
      <span class="dim" style="margin-left:8px">provider: ${esc(st.provider)}</span></h3>
      ${st.message ? `<p class="muted">${esc(st.message)}</p>` : ''}
      <div class="cam-wrap">
        <div class="cam-box" id="cam-box"><span class="dim">Camera preview</span></div>
        <div><p class="muted">Look at the camera in good light. Your photo is compared with your document photo and then
          <strong>deleted</strong>: we keep only the result.</p>
          <div class="btn-row"><button class="btn ghost" id="cam-start">Start camera</button>
            <button class="btn" id="cam-shot" disabled>Capture & verify</button></div>
          <p class="dim" style="margin-top:12px">No camera? Upload a photo instead:</p>
          <div class="field"><input id="bio-file" type="file" accept="image/jpeg,image/png" /></div>
          <button class="btn small ghost" id="bio-upload">Verify with uploaded photo</button>
        </div>
      </div>
      <p class="msg" id="bio-msg"></p>
      ${st.status === 'passed' ? '<div class="btn-row"><a class="btn" href="#credential">Continue to my credential</a></div>' : ''}
    </div>`;
  const video = document.createElement('video');
  video.autoplay = true; video.playsInline = true; video.muted = true;
  document.getElementById('cam-start').onclick = async () => {
    try {
      camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
      video.srcObject = camStream;
      const box = document.getElementById('cam-box');
      box.innerHTML = ''; box.appendChild(video);
      document.getElementById('cam-shot').disabled = false;
    } catch (e) { showMsg('bio-msg', 'Camera not available. Upload a photo instead.', 'err'); }
  };
  document.getElementById('cam-shot').onclick = (e) => busy(e.currentTarget, async () => {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640; canvas.height = video.videoHeight || 480;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.9));
    stopCamera();
    await sendSelfie(new File([blob], 'selfie.jpg', { type: 'image/jpeg' }));
  });
  document.getElementById('bio-upload').onclick = (e) => busy(e.currentTarget, async () => {
    const f = document.getElementById('bio-file').files[0];
    if (!f) return showMsg('bio-msg', 'Choose a photo first.', 'err');
    await sendSelfie(f);
  });
}

async function sendSelfie(file) {
  try {
    const form = new FormData();
    form.append('selfie', file);
    const r = await api('/biometric/start', { method: 'POST', form });
    showMsg('bio-msg', r.message || r.status, r.status === 'passed' ? 'ok' : 'err');
    if (r.status === 'passed') setTimeout(route, 900);
  } catch (err) { showMsg('bio-msg', err.message, 'err'); }
}

// ---------------------------------------------------------------- credential
async function renderCredential() {
  const elig = await api('/eligibility');
  let cred = null;
  try { cred = await api('/credentials/current'); } catch (e) { /* none */ }
  const active = cred && ['active', 'in_transition'].includes(cred.state);
  const token = cred ? cred.verification_url.split(/[/=]/).pop() : '';
  main.innerHTML = head('My credential', 'A time-limited platform credential. Not a government ID: each service applies its own policy.') + `
    <div class="dash-split">
      <div class="panel anim"><h3>Eligibility</h3>
        <ul class="checklist">${elig.items.map((i) => `<li><span class="tick ${i.passed ? 'done' : 'todo'}">
          <i class="fa-solid ${i.passed ? 'fa-check' : 'fa-hourglass-half'}"></i></span>${esc(i.label)}
          ${statusChip(i.status, i.passed ? 'positive' : 'neutral')}</li>`).join('')}</ul>
        ${!active ? `<div class="btn-row"><button class="btn" id="issue" ${elig.eligible ? '' : 'disabled'}>Issue my temporary credential</button></div>` : ''}
        <p class="msg" id="cred-msg"></p>
      </div>
      <div class="panel anim"><h3>Credential</h3>
        ${cred ? `<div class="cred-big">
          <div class="cred-row"><span class="cred-brand">Temporary Platform Credential</span>${statusChip(cred.state, active ? 'positive' : 'conflict')}</div>
          <div class="cred-row" style="margin-top:14px"><div>
            <p class="lbl">Credential ID</p><p class="val">${esc(cred.public_credential_id)}</p>
            <p class="lbl">Evidence / biometric</p><p class="val">${esc(cred.evidence_status.replace(/_/g, ' '))} · ${esc(cred.biometric_status)}</p>
            <p class="lbl">Issued · Expires</p><p class="val">${fmtDate(cred.issued_at)} · ${fmtDate(cred.expires_at)}</p>
          </div><img class="qr-img" id="big-qr" alt="Credential QR code"></div>
          <p class="dim" style="margin-top:12px">${esc(cred.disclaimer)}</p>
        </div>
        <div class="btn-row"><a class="btn ghost small" href="verify.html?token=${encodeURIComponent(token)}" target="_blank">Open verifier view</a></div>
        ${cred.attestation ? `<p style="margin-top:14px">On-chain attestation (${esc(cred.attestation.network)}): ${statusChip(cred.attestation.status,
          cred.attestation.status === 'confirmed' ? 'positive' : cred.attestation.status === 'failed' ? 'conflict' : 'warn')}
          ${cred.attestation.explorer_url ? `<br><a class="mono" href="${esc(cred.attestation.explorer_url)}" target="_blank" rel="noopener">${esc(cred.attestation.transaction_hash)}</a>` : ''}</p>` : ''}`
        : '<p class="muted">No credential yet. Complete the checklist, then issue it.</p>'}
      </div>
    </div>`;
  if (cred) loadQr('big-qr');
  const btn = document.getElementById('issue');
  if (btn) btn.onclick = () => busy(btn, async () => {
    try { await api('/credentials', { method: 'POST' }); await route(); }
    catch (err) { showMsg('cred-msg', err.message, 'err'); }
  });
}

// ---------------------------------------------------------------- health
async function renderHealth() {
  const docs = await api('/documents');
  main.innerHTML = head('Document health', 'Expiry dates, reminders and renewals. Renewing a document never erases your identity.') + `
    <div class="panel anim"><div class="tbl-wrap"><table class="tbl"><tr><th>Document</th><th>Expiry</th><th>Days left</th><th>Status</th><th></th></tr>
    ${docs.filter((d) => d.expiry_date).map((d) => `<tr><td>${esc(DOC_LABEL[d.document_type])}</td><td>${fmtDate(d.expiry_date)}</td>
      <td>${d.days_left ?? '—'}</td><td>${statusChip(d.renewal_status.replace(/_/g, ' '), d.renewal_status === 'current' ? 'positive' : 'warn')}</td>
      <td>${d.renewal_status === 'current' ? `<button class="btn small ghost" data-renew="${d.id}">Mark renewal in progress</button>` : ''}</td></tr>`).join('')
      || '<tr><td colspan="5" class="muted">No documents with expiry dates yet.</td></tr>'}</table></div>
      <div class="btn-row"><button class="btn ghost" id="run-reminders">Check for upcoming expiries</button></div>
      <p class="msg" id="health-msg"></p></div>`;
  main.querySelectorAll('[data-renew]').forEach((b) => (b.onclick = () => busy(b, async () => {
    await api(`/documents/${b.dataset.renew}/renewal`, { method: 'POST' });
    await renderHealth();
    showMsg('health-msg', 'Marked as renewal in progress. Your credential stays active meanwhile.', 'ok');
  })));
  document.getElementById('run-reminders').onclick = (e) => busy(e.currentTarget, async () => {
    const r = await api('/notifications/run-expiry-check', { method: 'POST' });
    showMsg('health-msg', `${r.created} new reminder(s) created. See Notifications.`, 'ok');
    await loadMe();
  });
}

// ---------------------------------------------------------------- notifications
async function renderNotifications() {
  const notes = await api('/notifications');
  main.innerHTML = head('Notifications', 'Reminders and actions that need your attention.') + `
    <div class="panel anim">${notes.map(noticeHtml).join('') || '<p class="muted">No notifications yet.</p>'}</div>`;
  await Promise.all(notes.filter((n) => !n.read).map((n) => api(`/notifications/${n.id}/read`, { method: 'POST' }).catch(() => {})));
}

const RENDER = {
  overview: renderOverview, identity: renderIdentity, documents: renderDocuments, consistency: renderConsistency,
  biometric: renderBiometric, credential: renderCredential, health: renderHealth, notifications: renderNotifications,
};

window.addEventListener('hashchange', route);
document.addEventListener('DOMContentLoaded', () => {
  if (sessionStorage.getItem('tawashir_auth') === 'true') route();
});
