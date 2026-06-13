"""Vendor console UI — the SPA template string only.

Holds INDEX_TEMPLATE (HTML + CSS + JS) for serial_admin.py. Deliberately
logic-free and free of any import from serial_admin (avoids an import cycle),
so the UI can be edited and visually reviewed without touching the routes.
"""

INDEX_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DentaCare — License Console</title>
<style>
  :root{
    --bg:#f6f8fb; --surface:#ffffff; --line:#e3e9f0; --ink:#16212e; --muted:#64748b;
    --brand:#0f6d7b; --accent:#13b5a7; --ok:#1f9d6b; --warn:#c2410c; --danger:#dc2626;
    --radius:12px; --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.10);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif}
  .app{display:flex;min-height:100vh}
  .sidebar{width:230px;flex:0 0 230px;background:var(--surface);border-right:1px solid var(--line);
           display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
  .brand{display:flex;align-items:center;gap:10px;padding:18px 18px 14px;font-weight:700}
  .brand .dot{width:10px;height:10px;border-radius:50%;background:var(--accent)}
  .brand small{display:block;font-weight:500;color:var(--muted);font-size:.72rem;letter-spacing:.4px}
  nav.nav{display:flex;flex-direction:column;gap:2px;padding:8px}
  .nav a{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;
         color:var(--ink);text-decoration:none;font-size:.9rem;cursor:pointer}
  .nav a:hover{background:#eef3f8}
  .nav a.active{background:var(--brand);color:#fff}
  .sidebar .foot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--line);
                 font-size:.78rem;color:var(--muted);display:flex;flex-direction:column;gap:6px}
  .statusdot{display:inline-flex;align-items:center;gap:7px}
  .statusdot .d{width:9px;height:9px;border-radius:50%;background:var(--muted)}
  .statusdot.ok .d{background:var(--ok)} .statusdot.bad .d{background:var(--danger)}
  .statusdot.warn .d{background:var(--warn)}
  .content{flex:1;min-width:0;padding:26px 30px;max-width:1100px}
  .view[hidden]{display:none}
  .page-h{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 18px}
  .page-h h1{font-size:1.35rem;margin:0} .page-h p{margin:2px 0 0;color:var(--muted);font-size:.88rem}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
        box-shadow:var(--shadow);padding:18px}
  .grid{display:grid;gap:16px}
  @media(min-width:680px){.grid-2{grid-template-columns:1fr 1fr}.grid-3{grid-template-columns:repeat(3,1fr)}}
  .stat{display:flex;flex-direction:column;gap:4px}
  .stat .n{font-size:1.9rem;font-weight:700;line-height:1}
  .stat .l{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.5px}
  label{display:block;font-size:.82rem;color:var(--muted);margin:12px 0 4px}
  input,select,textarea{width:100%;background:#fff;color:var(--ink);border:1px solid var(--line);
    border-radius:9px;padding:9px 11px;font:inherit}
  input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:var(--accent)}
  textarea{min-height:84px;font-family:ui-monospace,monospace}
  .btn{display:inline-flex;align-items:center;gap:7px;background:var(--brand);color:#fff;border:0;
       border-radius:9px;padding:10px 16px;font:inherit;font-weight:600;cursor:pointer}
  .btn:hover{filter:brightness(1.06)} .btn:disabled{opacity:.55;cursor:not-allowed}
  .btn.secondary{background:transparent;color:var(--ink);border:1px solid var(--line)}
  .btn.danger{background:var(--danger)} .btn.sm{padding:5px 10px;font-size:.8rem;font-weight:600}
  .row-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:14px}
  .mono{font-family:ui-monospace,monospace}
  .muted{color:var(--muted)} .field-err{color:var(--danger);font-size:.78rem;margin-top:4px}
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.74rem;font-weight:600;
         border:1px solid transparent}
  .badge.active{background:#e7f6ef;color:var(--ok);border-color:#bfe6d3}
  .badge.revoked{background:#fdeaea;color:var(--danger);border-color:#f4c5c5}
  .badge.suspended{background:#fdeede;color:var(--warn);border-color:#f3d4a8}
  .badge.expired{background:#eef1f5;color:var(--muted);border-color:var(--line)}
  .badge.local{background:#eef1f5;color:#475569;border-color:var(--line)}
  .badge.published{background:#e6f6f4;color:var(--brand);border-color:#bfe6e0}
  table{width:100%;border-collapse:collapse;margin-top:4px}
  thead th{position:sticky;top:0;background:var(--surface);text-align:left;padding:10px;
           font-size:.74rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);
           border-bottom:1px solid var(--line)}
  tbody td{padding:10px;border-bottom:1px solid var(--line);font-size:.86rem;vertical-align:middle}
  tbody tr:hover{background:#f9fbfd}
  .bar{height:6px;border-radius:4px;background:#eef1f5;overflow:hidden;min-width:60px}
  .bar > i{display:block;height:100%;background:var(--accent)}
  .chips{display:flex;gap:7px;flex-wrap:wrap;margin:6px 0 14px}
  .chip{padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;
        font-size:.8rem;cursor:pointer;color:var(--muted)}
  .chip.on{background:var(--brand);color:#fff;border-color:var(--brand)}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
  .toolbar input[type=search]{max-width:300px}
  .empty{text-align:center;color:var(--muted);padding:40px 16px}
  .table-wrap{overflow-x:auto}
  .toasts{position:fixed;right:18px;bottom:18px;display:flex;flex-direction:column;gap:10px;z-index:50}
  .toast{background:var(--ink);color:#fff;padding:11px 15px;border-radius:10px;box-shadow:var(--shadow);
         font-size:.86rem;max-width:340px;animation:slidein .18s ease-out}
  .toast.ok{background:#0d3b2e} .toast.err{background:#5b1414}
  @keyframes slidein{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}
  .drawer{position:fixed;inset:0;background:rgba(16,24,40,.34);display:flex;justify-content:flex-end;z-index:40}
  .drawer[hidden]{display:none}
  .drawer .panel{width:min(440px,92vw);background:var(--surface);height:100%;padding:22px;overflow:auto;box-shadow:var(--shadow)}
  .drawer dl{display:grid;grid-template-columns:auto 1fr;gap:8px 14px;font-size:.85rem;margin:14px 0}
  .drawer dt{color:var(--muted)} .drawer dd{margin:0;word-break:break-all}
  @media(max-width:760px){
    .app{flex-direction:column}
    .sidebar{width:100%;height:auto;flex:none;position:static;flex-direction:row;flex-wrap:wrap;align-items:center}
    nav.nav{flex-direction:row;flex:1} .sidebar .foot{margin:0;border:0;flex-direction:row;gap:14px}
    .content{padding:18px}
  }
</style></head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand"><span class="dot"></span><div>DentaCare<small>License Console</small></div></div>
    <nav class="nav" id="nav">
      <a data-view="dashboard" class="active" onclick="showView('dashboard')">Dashboard</a>
      <a data-view="issue" onclick="showView('issue')">Issue serials</a>
      <a data-view="licenses" onclick="showView('licenses')">Licenses</a>
      <a data-view="settings" onclick="showView('settings')">Settings</a>
    </nav>
    <div class="foot">
      <span class="statusdot" id="dot-key"><span class="d"></span><span id="dot-key-t">Key…</span></span>
      <span class="statusdot" id="dot-cloud"><span class="d"></span><span id="dot-cloud-t">Cloud…</span></span>
      <span style="opacity:.7">loopback only</span>
    </div>
  </aside>
  <main class="content">
    <section id="view-dashboard" class="view"></section>
    <section id="view-issue" class="view" hidden></section>
    <section id="view-licenses" class="view" hidden></section>
    <section id="view-settings" class="view" hidden></section>
  </main>
</div>
<div class="toasts" id="toasts"></div>
<div class="drawer" id="drawer" hidden onclick="if(event.target===this)closeDrawer()">
  <div class="panel" id="drawer-panel"></div>
</div>
<script>
/* JS CORE — Task 5 */
const state = { conn:{cloud_url:'', admin_token:''}, remember:false,
                key:{has_key:false}, cloud:{reachable:false, authorized:false, count:0},
                history:[], registry:[] };

function el(id){ return document.getElementById(id); }
function fmtDate(s){ return s ? String(s).slice(0,10) : ''; }
function esc(s){ const d=document.createElement('div'); d.textContent = s==null?'':String(s); return d.innerHTML.replace(/"/g,'&quot;'); }  /* encode " too, so esc() is safe inside value="..." / title="..." attributes */

function toast(msg, kind){
  const t = document.createElement('div');
  t.className = 'toast ' + (kind==='err'?'err':kind==='ok'?'ok':'');
  t.textContent = msg;
  el('toasts').appendChild(t);
  setTimeout(()=>{ t.remove(); }, 4200);
}

async function api(path, opts){
  try{
    const res = await fetch(path, opts);
    let body = {};
    try{ body = await res.json(); }catch(e){ body = {}; }
    return { ok: res.ok, status: res.status, body };
  }catch(e){
    return { ok:false, status:0, body:{ error:'Network error: ' + e } };
  }
}
function jsonPost(payload){
  return { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) };
}

const VIEW_LOADERS = {
  dashboard: loadDashboard, issue: loadIssue, licenses: loadLicenses, settings: loadSettingsView
};
function showView(name){
  for(const sec of document.querySelectorAll('.view')) sec.hidden = (sec.id !== 'view-'+name);
  for(const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.view===name);
  (VIEW_LOADERS[name] || function(){})();
}

function connReady(){ return !!(state.conn.cloud_url && state.conn.admin_token); }
function requireConn(){
  if(connReady()) return true;
  toast('Connect to the cloud in Settings first.', 'err');
  showView('settings');
  return false;
}

/* settings rehydrate + cloud status */
async function loadSettings(){
  const { body } = await api('/api/settings');
  state.conn.cloud_url = body.cloud_url || '';
  state.remember = !!body.remember;
  if(body.admin_token) state.conn.admin_token = body.admin_token;
  if(connReady()) pingCloud();
  else setCloudDot(false, false);
}
function setCloudDot(reachable, authorized, count){
  const dot = el('dot-cloud'), t = el('dot-cloud-t');
  dot.className = 'statusdot ' + (authorized ? 'ok' : reachable ? 'warn' : 'bad');
  t.textContent = authorized ? ('Cloud · ' + (count||0)) : reachable ? 'Cloud · unauthorized' : 'Cloud · offline';
}
async function pingCloud(){
  const { body } = await api('/api/cloud/ping', jsonPost(state.conn));
  state.cloud = { reachable:!!body.reachable, authorized:!!body.authorized, count:body.count||0 };
  setCloudDot(state.cloud.reachable, state.cloud.authorized, state.cloud.count);
  return state.cloud;
}

/* signing key */
async function refreshKey(){
  const { body } = await api('/api/key/status');
  state.key = body;
  const dot = el('dot-key'), t = el('dot-key-t');
  dot.className = 'statusdot ' + (body.has_key ? 'ok' : 'warn');
  t.textContent = body.has_key ? 'Key loaded' : 'No key';
}
async function generateKey(){
  const exists = state.key && state.key.has_key;
  if(exists && !confirm('Rotating the key invalidates every serial already issued. Continue?')) return;
  const { ok, body } = await api('/api/key/generate', jsonPost({ confirm_overwrite: exists }));
  if(!ok){ toast(body.error || 'Could not generate a key.', 'err'); return; }
  toast('Signing key ready.', 'ok');
  await refreshKey();
  if(!document.getElementById('view-settings').hidden) loadSettingsView();
}

/* ---- Settings view ---- */
function loadSettingsView(){
  const keyBlock = state.key && state.key.has_key
    ? '<div class="muted">Key loaded.</div>'
      + '<label>Public key</label><div class="mono" style="word-break:break-all;font-size:.8rem">'
        + esc(state.key.public_key||'') + '</div>'
      + '<div class="row-actions"><button class="btn secondary" onclick="copyText(this,\'' + esc(state.key.public_key||'') + '\')">Copy public key</button>'
      + '<button class="btn secondary" onclick="generateKey()">Rotate keypair</button></div>'
      + '<div class="field-err">Rotating invalidates every serial already issued.</div>'
    : '<div class="muted">No signing key yet — generate one to start minting.</div>'
      + '<div class="row-actions"><button class="btn" onclick="generateKey()">Generate keypair</button></div>';
  el('view-settings').innerHTML =
    '<div class="page-h"><div><h1>Settings</h1><p>Signing key and the shared cloud connection.</p></div></div>'
    + '<div class="grid grid-2">'
    + '  <div class="card"><h3 style="margin-top:0">Signing key</h3>' + keyBlock + '</div>'
    + '  <div class="card"><h3 style="margin-top:0">Cloud connection</h3>'
    + '    <label>Cloud URL</label><input id="s-url" value="' + esc(state.conn.cloud_url) + '">'
    + '    <label>Admin token (X-Admin-Token)</label><input id="s-token" type="password" placeholder="CLINIC_ADMIN_API_TOKEN" value="' + esc(state.conn.admin_token) + '">'
    + '    <label style="display:flex;gap:8px;align-items:center;margin-top:12px;color:var(--ink)">'
    + '      <input type="checkbox" id="s-remember" style="width:auto" ' + (state.remember?'checked':'') + '> Remember on this machine</label>'
    + '    <div class="muted" style="font-size:.78rem">Saves the token to a 0600 file next to your signing key. Leave off to keep it in memory for this session only.</div>'
    + '    <div class="row-actions"><button class="btn" onclick="saveSettings()">Save</button>'
    + '      <button class="btn secondary" onclick="testConnection(this)">Test connection</button>'
    + '      <span id="s-conn" class="muted" style="font-size:.84rem"></span></div>'
    + '  </div>'
    + '</div>'
    + '<div class="card" style="margin-top:16px"><h3 style="margin-top:0">Security</h3>'
    + '  <ul class="muted" style="font-size:.85rem;margin:0;padding-left:18px">'
    + '    <li>The private signing seed never leaves this machine.</li>'
    + '    <li>Activation codes are secrets — don\'t commit the CSV/JSON you download.</li>'
    + '    <li>The settings file is 0600 and gitignored.</li></ul></div>';
}
function readSettingsForm(){
  state.conn.cloud_url = el('s-url').value.trim();
  state.conn.admin_token = el('s-token').value.trim();
  state.remember = el('s-remember').checked;
}
async function saveSettings(){
  readSettingsForm();
  const { body } = await api('/api/settings', jsonPost({
    cloud_url: state.conn.cloud_url, admin_token: state.conn.admin_token, remember: state.remember }));
  if(body.success){ toast('Settings saved.', 'ok'); pingCloud(); }
  else toast(body.error || 'Could not save settings.', 'err');
}
async function testConnection(btn){
  readSettingsForm();
  const out = el('s-conn');
  if(!state.conn.cloud_url){ out.textContent = 'Enter a cloud URL first.'; return; }
  btn.disabled = true; out.textContent = 'Testing…';
  const c = await pingCloud();
  btn.disabled = false;
  out.textContent = c.authorized ? ('Connected — ' + c.count + ' serial(s).')
    : c.reachable ? 'Reachable, but the admin token was rejected.'
    : 'Could not reach the cloud node.';
}
function copyText(btn, text){
  navigator.clipboard.writeText(text||'').then(()=>{ const o=btn.textContent; btn.textContent='Copied!';
    setTimeout(()=>btn.textContent=o, 1600); });
}
function closeDrawer(){ el('drawer').hidden = true; }

/* ---- Dashboard view ---- */
async function loadDashboard(){
  const { body } = await api('/api/history');
  state.history = (body && body.records) || [];
  const total = state.history.length;
  const published = state.history.filter(r=>r.published).length;
  const local = total - published;
  const keyTxt = state.key && state.key.has_key ? 'Loaded' : 'None';
  const cloudTxt = state.cloud.authorized ? ('Connected · ' + state.cloud.count)
                 : state.cloud.reachable ? 'Unauthorized' : 'Offline';
  const recent = state.history.slice(0,5);
  const recentRows = recent.map(r=>
    '<tr><td class="mono">' + esc(r.serial) + '</td><td>' + esc(r.clinic_name||'') + '</td>'
    + '<td>' + statusBadge(r.published?'published':'local') + '</td>'
    + '<td>' + fmtDate(r.expires_at) + '</td></tr>').join('');
  const recentBlock = total
    ? '<div class="card table-wrap"><h3 style="margin-top:0">Recent serials</h3><table>'
      + '<thead><tr><th>Serial</th><th>Clinic</th><th>Status</th><th>Expires</th></tr></thead>'
      + '<tbody>' + recentRows + '</tbody></table></div>'
    : '<div class="card empty"><h3>No serials yet</h3><p>Mint your first serial to get started.</p>'
      + '<button class="btn" onclick="showView(\'issue\')">Issue serials</button></div>';
  el('view-dashboard').innerHTML =
    '<div class="page-h"><div><h1>Dashboard</h1><p>Issued and published serials on this machine.</p></div>'
    + '<div class="row-actions" style="margin:0"><button class="btn" onclick="showView(\'issue\')">Issue serials</button>'
    + '<button class="btn secondary" onclick="showView(\'licenses\')">View licenses</button></div></div>'
    + '<div class="grid grid-3" style="margin-bottom:16px">'
    + statCard(total, 'Issued') + statCard(published, 'Published') + statCard(local, 'Local-only')
    + '</div>'
    + '<div class="grid grid-2" style="margin-bottom:16px">'
    + '<div class="card stat"><span class="l">Signing key</span><span class="n" style="font-size:1.2rem">' + keyTxt + '</span></div>'
    + '<div class="card stat"><span class="l">Cloud</span><span class="n" style="font-size:1.2rem">' + cloudTxt + '</span></div>'
    + '</div>'
    + recentBlock;
}
function statCard(n, label){
  return '<div class="card stat"><span class="n">' + n + '</span><span class="l">' + label + '</span></div>';
}
function statusBadge(kind){
  const map = { active:'active', revoked:'revoked', suspended:'suspended', expired:'expired',
                local:'local', published:'published' };
  const cls = map[kind] || 'local';
  const txt = kind==='local' ? 'local only' : kind;
  return '<span class="badge ' + cls + '">' + txt + '</span>';
}

/* ---- Issue view ---- */
let lastRecords = [];
function loadIssue(){
  el('view-issue').innerHTML =
    '<div class="page-h"><div><h1>Issue serials</h1><p>Mint signed serials for a clinic and publish them for short-serial activation.</p></div></div>'
    + '<div class="card">'
    + '  <div class="grid grid-2">'
    + '    <div><label>Clinic name</label><input id="m-name" placeholder="Smile Dental"><div class="field-err" id="e-name" hidden></div></div>'
    + '    <div><label>Clinic code (≤4)</label><input id="m-code" maxlength="4" placeholder="SMD"><div class="field-err" id="e-code" hidden></div></div>'
    + '    <div><label>Plan</label><select id="m-plan"><option>Standard</option><option>Premium</option><option>Enterprise</option></select></div>'
    + '    <div><label>Expiry (days)</label><input id="m-expiry" type="number" value="365"></div>'
    + '    <div><label>Max devices</label><input id="m-max" type="number" value="3"></div>'
    + '  </div>'
    + '  <label>Device IDs (one per line — blank = one clinic-level serial)</label>'
    + '  <textarea id="m-devices" placeholder="LAPTOP-01&#10;PHONE-02"></textarea>'
    + '  <div class="row-actions"><button class="btn" onclick="mint()">Mint serials</button></div>'
    + '  <div class="muted" style="font-size:.8rem;margin-top:8px">Give the clinic owner the <b>Serial Number</b> — they type it in the app to activate online. The full Activation Code is the offline fallback.</div>'
    + '</div>'
    + '<div id="results" style="margin-top:16px"></div>';
}
function validateIssue(b){
  let ok = true;
  const setErr = (id, msg)=>{ const e=el(id); e.hidden=!msg; e.textContent=msg||''; if(msg) ok=false; };
  setErr('e-name', b.clinic_name ? '' : 'Clinic name is required.');
  setErr('e-code', (b.clinic_code && b.clinic_code.length<=4) ? '' : 'Clinic code is required (1–4 characters).');
  return ok;
}
function collectIssue(){
  return {
    clinic_name: el('m-name').value.trim(),
    clinic_code: el('m-code').value.trim(),
    plan_name: el('m-plan').value,
    expiry_days: parseInt(el('m-expiry').value || '365', 10),
    max_devices: parseInt(el('m-max').value || '1', 10),
    devices: el('m-devices').value
  };
}
async function mint(){
  const b = collectIssue();
  if(!validateIssue(b)) return;
  const { ok, body } = await api('/api/mint', jsonPost(b));
  if(!ok){ toast(body.error || 'Mint failed.', 'err'); return; }
  lastRecords = body.records || [];
  renderResults();
  toast('Minted ' + lastRecords.length + ' serial(s).', 'ok');
}
function renderResults(){
  if(!lastRecords.length){ el('results').innerHTML = ''; return; }
  const rows = lastRecords.map((r,i)=>
    '<tr><td class="mono">' + esc(r.serial) + '</td><td>' + fmtDate(r.expires_at) + '</td>'
    + '<td><button class="btn secondary sm" onclick="copyText(this,' + jsArg(r.serial) + ')">Copy serial</button> '
    + '<button class="btn secondary sm" onclick="copyText(this,' + jsArg(r.offline_token) + ')">Copy activation code</button></td></tr>').join('');
  el('results').innerHTML =
    '<div class="card table-wrap"><div class="toolbar"><h3 style="margin:0;flex:1">Results</h3>'
    + '<button class="btn secondary sm" onclick="downloadJson()">Download JSON</button>'
    + '<button class="btn secondary sm" onclick="downloadCsv()">Download CSV</button>'
    + '<button class="btn sm" onclick="publishAll(this)">Publish all to cloud</button></div>'
    + '<table><thead><tr><th>Serial number</th><th>Expires</th><th>Actions</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
}
function jsArg(s){ return JSON.stringify(String(s==null?'':s)).replace(/&/g,'&amp;').replace(/"/g,'&quot;'); }  /* JSON-encode for the JS layer, then HTML-encode &/" so the result is safe inside a double-quoted onclick="..." attribute (the browser decodes &quot; back to " before the handler runs) */
async function publishAll(btn){
  if(!lastRecords.length){ toast('Mint serials first.', 'err'); return; }
  if(!requireConn()) return;
  btn.disabled = true; btn.textContent = 'Publishing…';
  const { ok, body } = await api('/api/upload-cloud', jsonPost(Object.assign(
    { records: lastRecords }, state.conn)));
  btn.disabled = false; btn.textContent = 'Publish all to cloud';
  if(!ok){ toast(body.error || 'Upload failed.', 'err'); return; }
  const fails = (body.results || []).filter(r=>!r.ok);
  toast('Published ' + body.ok_count + '/' + body.total + ' serial(s).' + (fails.length?' Some failed.':''),
        fails.length ? 'err' : 'ok');
  pingCloud();
}
function _download(name, type, text){
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}
function downloadJson(){ _download('serials.json', 'application/json', JSON.stringify(lastRecords, null, 2)); }
function downloadCsv(){
  const head = ['Serial','Device ID','Plan','Max Devices','Issued At','Expires At','Offline Token'];
  const rows = lastRecords.map(r=>[r.serial,r.device_id,r.plan_name,r.max_devices,r.issued_at,r.expires_at,r.offline_token]);
  const csv = [head].concat(rows).map(c=>c.map(x=>'"'+String(x==null?'':x).replace(/"/g,'""')+'"').join(',')).join('\r\n');
  _download('serials.csv', 'text/csv', csv);
}

/* placeholder loader — replaced in Task 7 */
function loadLicenses(){ el('view-licenses').innerHTML = '<div class="page-h"><h1>Licenses</h1></div><div class="card empty">Coming up next.</div>'; }

document.addEventListener('DOMContentLoaded', async ()=>{
  await refreshKey();
  await loadSettings();
  showView('dashboard');
});
</script>
</body></html>'''
