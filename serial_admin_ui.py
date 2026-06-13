"""Vendor console UI — the SPA template string only.

Holds INDEX_TEMPLATE (HTML + CSS + JS) for serial_admin.py. Deliberately
logic-free and free of any import from serial_admin (avoids an import cycle),
so the UI can be edited and visually reviewed without touching the routes.
"""

INDEX_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Serial Minter — Vendor Console</title>
<style>
  :root { --bg:#0f1722; --panel:#16212e; --line:#243446; --ink:#e7eef6; --muted:#8aa0b4;
          --accent:#3ddc97; --warn:#ff6b6b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif; }
  header { padding:18px 22px; border-bottom:1px solid var(--line); display:flex;
           align-items:baseline; gap:12px; }
  header h1 { font-size:1.1rem; margin:0; letter-spacing:.3px; }
  header .tag { color:var(--muted); font-size:.85rem; }
  main { max-width:980px; margin:0 auto; padding:22px; display:grid; gap:18px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px; }
  .panel h2 { margin:0 0 12px; font-size:.95rem; color:var(--muted); text-transform:uppercase;
              letter-spacing:.6px; }
  label { display:block; font-size:.82rem; color:var(--muted); margin:10px 0 4px; }
  input, select, textarea { width:100%; background:#0c141d; color:var(--ink);
    border:1px solid var(--line); border-radius:8px; padding:9px 10px; font:inherit; }
  textarea { min-height:84px; font-family:ui-monospace,monospace; }
  .grid { display:grid; gap:12px; }
  @media (min-width:720px){ .grid-2 { grid-template-columns:1fr 1fr; } }
  button { background:var(--accent); color:#06281b; border:0; border-radius:8px;
    padding:10px 16px; font:inherit; font-weight:600; cursor:pointer; margin-top:14px; }
  button.ghost { background:transparent; color:var(--ink); border:1px solid var(--line); }
  .pub { font-family:ui-monospace,monospace; word-break:break-all; color:var(--accent); }
  table { width:100%; border-collapse:collapse; margin-top:8px; display:block; overflow-x:auto; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); font-size:.85rem; }
  .tok { font-family:ui-monospace,monospace; max-width:260px; overflow:hidden;
         text-overflow:ellipsis; white-space:nowrap; }
  .warn { color:var(--warn); font-size:.82rem; margin-top:8px; }
  .muted { color:var(--muted); }
</style></head>
<body>
<header><h1>Serial Minter</h1><span class="tag">vendor console · loopback only</span></header>
<main>
  <section class="panel" id="key-panel">
    <h2>Signing key</h2>
    <div id="key-status" class="muted">Checking…</div>
    <div id="key-pub" class="pub" style="display:none"></div>
    <button class="ghost" id="key-gen" onclick="generateKey()">Generate keypair</button>
    <div class="warn">The private seed never leaves this machine. Only the public key is shown.</div>
  </section>
  <section class="panel">
    <h2>Mint serials</h2>
    <form id="mint-form" onsubmit="return false;">
      <div class="grid grid-2">
        <div><label>Clinic name</label><input id="m-name" placeholder="Smile Dental"></div>
        <div><label>Clinic code (≤4)</label><input id="m-code" maxlength="4" placeholder="SMD"></div>
        <div><label>Plan</label>
          <select id="m-plan"><option>Standard</option><option>Premium</option><option>Enterprise</option></select></div>
        <div><label>Expiry (days)</label><input id="m-expiry" type="number" value="365"></div>
        <div><label>Max devices</label><input id="m-max" type="number" value="3"></div>
      </div>
      <label>Device IDs (one per line — blank = one clinic-level serial)</label>
      <textarea id="m-devices" placeholder="LAPTOP-01&#10;PHONE-02"></textarea>
      <button onclick="mint()">Mint</button>
    </form>
    <div class="warn">Minted tokens are secrets — don't commit the CSV/JSON you download.</div>
  </section>
  <section class="panel" id="results-panel" style="display:none">
    <h2>Results</h2>
    <div>
      <button class="ghost" onclick="downloadJson()">Download JSON</button>
      <button class="ghost" onclick="downloadCsv()">Download CSV</button>
    </div>
    <p style="font-size:.82rem;color:#8aa0b4;margin:8px 0 4px">Give the clinic owner the <b style="color:#3ddc97">Serial Number</b> only — they type it in the app and it activates online. (The full Activation Code is the offline fallback.)</p>
    <table id="results"><thead><tr><th>Serial Number</th><th>Expires</th><th>Activation Code</th><th></th></tr></thead><tbody></tbody></table>
    <div style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px;">
      <h2 style="margin-bottom:8px;">Publish to cloud (enable short-serial activation)</h2>
      <p class="muted" style="font-size:.82rem;margin:0 0 8px;">Uploads these serials to the cloud registry so the clinic can activate by typing the short serial only. Needs the cloud admin token.</p>
      <div class="grid grid-2">
        <div><label>Cloud URL</label><input id="c-url" value="https://app.dentacare.tech"></div>
        <div><label>Admin token (X-Admin-Token)</label><input id="c-token" type="password" placeholder="CLINIC_ADMIN_API_TOKEN"></div>
      </div>
      <button onclick="uploadCloud()">Upload minted serials to cloud</button>
      <div id="c-result" class="muted" style="margin-top:8px;font-size:.85rem;"></div>
    </div>
  </section>
  <section class="panel" id="history-panel">
    <h2>Serial history — this machine</h2>
    <p class="muted" style="font-size:.82rem;margin:0 0 8px;">Every serial minted here is logged locally (with its Activation Code) so you never lose track. Saved in <span class="pub" style="font-size:.8rem;">minted_serials.db</span> next to your signing key.</p>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <button class="ghost" style="margin-top:0" onclick="loadHistory()">Refresh</button>
      <button class="ghost" style="margin-top:0" onclick="exportHistory()">Export all (CSV)</button>
      <span id="hist-count" class="muted" style="font-size:.82rem;"></span>
    </div>
    <table id="history"><thead><tr><th>Serial Number</th><th>Clinic</th><th>Plan</th><th>Expires</th><th>Cloud</th><th></th></tr></thead><tbody></tbody></table>
  </section>
  <section class="panel" id="publish-panel">
    <h2>Publish an existing serial to the cloud</h2>
    <p class="muted" style="font-size:.82rem;margin:0 0 8px;">Paste a serial's full Activation Code to register it on the cloud so the clinic can activate by typing the short serial. Use this for serials minted before this machine kept a history. Needs the cloud admin token.</p>
    <div class="grid grid-2">
      <div><label>Cloud URL</label><input id="cloud-url" value="https://app.dentacare.tech"></div>
      <div><label>Admin token (X-Admin-Token)</label><input id="cloud-admin" type="password" placeholder="CLINIC_ADMIN_API_TOKEN"></div>
    </div>
    <label>Activation Code (full offline token)</label>
    <textarea id="pub-token" placeholder="eyJ..."></textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button onclick="publishToken()">Publish to cloud</button>
      <button class="ghost" onclick="viewCloud()">View cloud registry</button>
    </div>
    <div id="pub-result" class="muted" style="margin-top:8px;font-size:.85rem;"></div>
    <table id="cloud-reg" style="display:none;margin-top:10px;"><thead><tr><th>Serial Number</th><th>Clinic</th><th>Status</th><th>Devices</th><th>Expires</th></tr></thead><tbody></tbody></table>
  </section>
</main>
<script>
  let lastRecords = [];
  let histRows = [];
  function fmtDate(s) { return s ? String(s).slice(0, 10) : ''; }
  function _cloudConn() {
    return { cloud_url: document.getElementById('cloud-url').value.trim(),
             admin_token: document.getElementById('cloud-admin').value.trim() };
  }
  async function loadHistory() {
    let body;
    try { body = await fetch('/api/history').then(r => r.json()); }
    catch (e) { document.getElementById('hist-count').textContent = 'Could not load history.'; return; }
    histRows = (body && body.records) || [];
    const tb = document.querySelector('#history tbody');
    tb.innerHTML = '';
    for (const r of histRows) {
      const tr = document.createElement('tr');
      const cells = [r.serial, r.clinic_name || '', r.plan_name || '', fmtDate(r.expires_at), r.published ? 'published' : 'local only'];
      for (let i = 0; i < cells.length; i++) {
        const td = document.createElement('td'); td.textContent = cells[i];
        if (i === 0) { td.style.fontFamily = 'ui-monospace,monospace'; td.style.fontWeight = '600'; }
        if (i === 4 && !r.published) td.style.color = 'var(--warn)';
        tr.appendChild(td);
      }
      const act = document.createElement('td');
      const copy = document.createElement('button'); copy.className = 'ghost'; copy.textContent = 'Copy Code';
      copy.style.cssText = 'padding:5px 10px;font-size:.8rem;margin:0';
      copy.onclick = () => { navigator.clipboard.writeText(r.offline_token || '').then(() => { copy.textContent = 'Copied!'; setTimeout(() => copy.textContent = 'Copy Code', 2000); }); };
      act.appendChild(copy);
      if (!r.published) {
        const pb = document.createElement('button'); pb.className = 'ghost'; pb.textContent = 'Publish';
        pb.style.cssText = 'padding:5px 10px;font-size:.8rem;margin:0 0 0 6px';
        pb.onclick = () => publishExisting(r.offline_token, pb); act.appendChild(pb);
      }
      tr.appendChild(act); tb.appendChild(tr);
    }
    document.getElementById('hist-count').textContent = histRows.length + ' serial(s) logged.';
  }
  async function publishExisting(token, btn) {
    const conn = _cloudConn();
    if (!conn.admin_token) { alert('Enter the cloud admin token (in the panel below) first.'); return; }
    if (btn) { btn.disabled = true; btn.textContent = 'Publishing…'; }
    try {
      const res = await fetch('/api/publish-token', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ offline_token: token }, conn)) });
      const body = await res.json();
      if (!res.ok || !(body.result && body.result.ok)) { alert(body.error || (body.result && body.result.error) || 'Publish failed.'); }
    } catch (e) { alert('Network error: ' + e); }
    if (btn) { btn.disabled = false; btn.textContent = 'Publish'; }
    loadHistory();
  }
  async function publishToken() {
    const token = document.getElementById('pub-token').value.trim();
    const out = document.getElementById('pub-result');
    if (!token) { out.textContent = 'Paste an Activation Code first.'; return; }
    const conn = _cloudConn();
    if (!conn.admin_token) { out.textContent = 'Enter the cloud admin token first.'; return; }
    out.textContent = 'Publishing…';
    try {
      const res = await fetch('/api/publish-token', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ offline_token: token }, conn)) });
      const body = await res.json();
      if (!res.ok || !(body.result && body.result.ok)) { out.textContent = body.error || (body.result && body.result.error) || 'Publish failed.'; return; }
      out.textContent = 'Published ' + (body.serial || 'serial') + ' to the cloud. The clinic can now activate by short serial.';
      document.getElementById('pub-token').value = '';
      loadHistory();
    } catch (e) { out.textContent = 'Network error: ' + e; }
  }
  async function viewCloud() {
    const conn = _cloudConn();
    const out = document.getElementById('pub-result');
    if (!conn.admin_token) { out.textContent = 'Enter the cloud admin token first.'; return; }
    out.textContent = 'Loading cloud registry…';
    try {
      const res = await fetch('/api/cloud/serials', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(conn) });
      const body = await res.json();
      if (!res.ok) { out.textContent = body.error || 'Could not load registry.'; return; }
      const rows = body.serials || [];
      const tbl = document.getElementById('cloud-reg'); const tb = tbl.querySelector('tbody'); tb.innerHTML = '';
      for (const r of rows) {
        const tr = document.createElement('tr');
        const cells = [r.serial, r.clinic_name || '', r.status || '', (r.used_devices + '/' + r.max_devices), fmtDate(r.expires_at)];
        for (let i = 0; i < cells.length; i++) { const td = document.createElement('td'); td.textContent = cells[i]; if (i === 0) { td.style.fontFamily = 'ui-monospace,monospace'; } tr.appendChild(td); }
        tb.appendChild(tr);
      }
      tbl.style.display = rows.length ? '' : 'none';
      out.textContent = rows.length + ' serial(s) in the cloud registry.';
    } catch (e) { out.textContent = 'Network error: ' + e; }
  }
  function exportHistory() {
    if (!histRows.length) { alert('No history yet — mint a serial first.'); return; }
    const head = ['Serial', 'Clinic', 'Code', 'Device ID', 'Plan', 'Max Devices', 'Issued At', 'Expires At', 'Published', 'Offline Token'];
    const rows = histRows.map(r => [r.serial, r.clinic_name, r.clinic_code, r.device_id, r.plan_name, r.max_devices, r.issued_at, r.expires_at, (r.published ? 'yes' : 'no'), r.offline_token]);
    const csv = [head].concat(rows).map(cols => cols.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    _download('minted_serials_history.csv', 'text/csv', csv);
  }
  async function refreshKey() {
    const st = await fetch('/api/key/status').then(r => r.json());
    const el = document.getElementById('key-status');
    const pub = document.getElementById('key-pub');
    const gen = document.getElementById('key-gen');
    if (st.has_key) {
      el.textContent = 'Key loaded (' + (st.key_file || '') + '). Public key:';
      pub.style.display = ''; pub.textContent = st.public_key || '';
      gen.textContent = 'Rotate keypair';
    } else {
      el.textContent = 'No signing key yet — generate one to start minting.';
      pub.style.display = 'none'; gen.textContent = 'Generate keypair';
    }
  }
  async function generateKey() {
    const exists = document.getElementById('key-pub').style.display !== 'none';
    if (exists && !confirm('Rotating the key invalidates every serial already issued. Continue?')) return;
    const res = await fetch('/api/key/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm_overwrite: exists })
    });
    const body = await res.json();
    if (!res.ok) { alert(body.error || 'Could not generate a key.'); return; }
    await refreshKey();
  }
  function collectBody() {
    return {
      clinic_name: document.getElementById('m-name').value.trim(),
      clinic_code: document.getElementById('m-code').value.trim(),
      plan_name: document.getElementById('m-plan').value,
      expiry_days: parseInt(document.getElementById('m-expiry').value || '365', 10),
      max_devices: parseInt(document.getElementById('m-max').value || '1', 10),
      devices: document.getElementById('m-devices').value
    };
  }
  async function mint() {
    const res = await fetch('/api/mint', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectBody())
    });
    const body = await res.json();
    if (!res.ok) { alert(body.error || 'Mint failed.'); return; }
    lastRecords = body.records || [];
    const tb = document.querySelector('#results tbody');
    tb.innerHTML = '';
    for (const r of lastRecords) {
      const tr = document.createElement('tr');
      const sc = document.createElement('td'); sc.textContent = r.serial; sc.style.fontFamily = 'ui-monospace,monospace'; sc.style.fontWeight = '600';
      const ex = document.createElement('td'); ex.textContent = r.expires_at;
      const tok = document.createElement('td'); tok.className = 'tok'; tok.title = r.offline_token; tok.textContent = r.offline_token;
      const cp = document.createElement('td');
      const btn = document.createElement('button'); btn.className = 'ghost'; btn.textContent = 'Copy Code';
      btn.style.cssText = 'padding:5px 10px;font-size:.8rem;margin:0';
      btn.onclick = () => { navigator.clipboard.writeText(r.offline_token).then(() => { btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = 'Copy Code', 2000); }); };
      cp.appendChild(btn);
      tr.appendChild(sc); tr.appendChild(ex); tr.appendChild(tok); tr.appendChild(cp);
      tb.appendChild(tr);
    }
    document.getElementById('results-panel').style.display = lastRecords.length ? '' : 'none';
    loadHistory();
  }
  function _download(name, type, text) {
    const blob = new Blob([text], { type: type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    URL.revokeObjectURL(a.href);
  }
  async function uploadCloud() {
    if (!lastRecords.length) { alert('Mint serials first.'); return; }
    const out = document.getElementById('c-result');
    out.textContent = 'Uploading…';
    try {
      const res = await fetch('/api/upload-cloud', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: lastRecords,
          cloud_url: document.getElementById('c-url').value.trim(),
          admin_token: document.getElementById('c-token').value.trim()
        })
      });
      const body = await res.json();
      if (!res.ok) { out.textContent = body.error || 'Upload failed.'; return; }
      const fails = (body.results || []).filter(r => !r.ok);
      out.textContent = 'Uploaded ' + body.ok_count + ' / ' + body.total + ' serial(s).'
        + (fails.length ? ' Failed: ' + fails.map(f => f.serial + ' (' + (f.error || 'error') + ')').join(', ') : ' All good.');
      loadHistory();
    } catch (e) { out.textContent = 'Network error: ' + e; }
  }
  function downloadJson() { _download('serials.json', 'application/json', JSON.stringify(lastRecords, null, 2)); }
  function downloadCsv() {
    const head = ['Serial', 'Device ID', 'Plan', 'Max Devices', 'Issued At', 'Expires At', 'Offline Token'];
    const rows = lastRecords.map(r => [r.serial, r.device_id, r.plan_name, r.max_devices, r.issued_at, r.expires_at, r.offline_token]);
    const csv = [head].concat(rows).map(cols => cols.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\r\n');
    _download('serials.csv', 'text/csv', csv);
  }
  document.addEventListener('DOMContentLoaded', () => { refreshKey(); loadHistory(); });
</script>
</body></html>'''
