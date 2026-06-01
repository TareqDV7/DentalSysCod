# Odontogram — Desktop (web portal) Implementation Plan (Track B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the odontogram to the Flask web portal — a 32-tooth SVG arch on the patient profile, a tap-to-act popup (set condition · log treatment · add to plan), and a tooth-condition admin sheet under Administration — at parity with the mobile app.

**Architecture:** Pure additions to `templates.py` (the single-file HTML/CSS/JS SPA). The chart reads `GET /api/patients/<id>/tooth-chart` (Track A) and writes via `POST .../tooth-chart`, the catalog routes, and the existing follow-up + treatment-plan forms. No new files.

**Tech Stack:** Vanilla JS + inline SVG inside `templates.py`'s `HTML_TEMPLATE`; EN/AR i18n via the `translations` object. Consistent with the repo's existing inline-JS style.

**Dependency:** **Track A (backend) must be merged and green first** — this track calls its endpoints. The frozen contract is `GET /api/patients/<id>/tooth-chart` → `{conditions:[…], teeth:{tooth_no:{condition_id,condition_name,color,note,source,unpaid_balance,has_plan}}}`.

**Spec:** `docs/superpowers/specs/2026-06-01-odontogram-design.md`

**Testing note:** Inline JS in this repo is **not unit-tested** (same as the existing expression/percentage features — see `docs/superpowers/specs/2026-05-31-percentage-discount-design.md`). Each task ends with an explicit **manual verification** run against a local server, reported honestly. Run the server with `py dental_clinic.py` (Windows) and open `http://localhost:5000` (login `admin`/`admin`).

---

## Key anchors in `templates.py` (verified 2026-06-01)

| What | Location |
|------|----------|
| Follow-up Add form (modal) | `~5590‑5645`; tooth input is `id="followup-tooth-no"` (`5610`) |
| Follow-up rows render | `renderFollowupsRows(followups)` `~5759`; table body `id="patient-followups-body"` (`5645`) |
| `translations` object | EN block opens `~2639`; AR block opens `~3135` |
| Procedure-catalog admin (pattern to mirror) | markup `~1887‑1894`; `renderProcedureCatalogTable()` `~3652` |
| Calc-field submit interceptor / `evalCalcField` | `~6359` (capture-phase) — relevant when pre-filling the follow-up form |

> The patient-profile view is the screen that renders `#patient-followups-body`. Locate the JS function that builds it (search for `patient-followups-body`) — the odontogram card is injected into that same view, above the follow-up sheet.

---

## File Structure

All changes are in `templates.py`:
- **CSS:** a small `<style>` block for the arch, teeth, badges, legend, popup.
- **Markup:** an odontogram `<section>` card inside the patient-profile view; a tooth-conditions admin card inside the Administration tab.
- **JS:** `renderOdontogram(patientId)`, `buildToothArchSvg(chart)`, `openToothPopup(...)`, condition-admin CRUD, and prefill helpers.
- **i18n:** new keys in both EN (`~2639`) and AR (`~3135`) blocks.

---

## Task 1: FDI arch geometry + condition color map (pure JS)

**Files:** Modify `templates.py` (JS, near the other render helpers ~`5759`)

- [ ] **Step 1: Add the FDI layout constant + helpers**

Add a JS block (place it just above `renderFollowupsRows`):

```javascript
// FDI permanent dentition, clinician's view (patient's right on the left).
const FDI_UPPER = ['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28'];
const FDI_LOWER = ['48','47','46','45','44','43','42','41','31','32','33','34','35','36','37','38'];

// Tooth class by FDI position (2nd digit): 1-2 incisor, 3 canine, 4-5 premolar, 6-8 molar.
function fdiToothClass(fdi) {
  const n = parseInt(fdi[1], 10);
  if (n <= 2) return 'incisor';
  if (n === 3) return 'canine';
  if (n <= 5) return 'premolar';
  return 'molar';
}

function isValidFdi(s) { return /^[1-4][1-8]$/.test(String(s || '')); }
```

- [ ] **Step 2: Manual verification**

Open the portal, open DevTools console, paste a call: `FDI_UPPER.length` → `16`; `fdiToothClass('16')` → `'molar'`; `fdiToothClass('11')` → `'incisor'`; `isValidFdi('51')` → `false`. Report results.

- [ ] **Step 3: Commit**

```bash
git add templates.py
git commit -m "feat(web): FDI arch layout + tooth-class helpers"
```

---

## Task 2: Tooth silhouette SVG + arch builder

**Files:** Modify `templates.py` (JS + CSS)

- [ ] **Step 1: Add the per-class tooth path templates**

Each tooth is a `<path>` in a 40×56 viewbox cell. These are real, distinct silhouettes per class (molar with cusps, pointed canine, blade incisor, rounded premolar). Add:

```javascript
// Tooth silhouettes in a 40x56 cell (crown on top, root tapering down).
// Distinct per class; refine visually in Task 9's review.
const TOOTH_PATHS = {
  molar:    'M6,10 Q8,4 12,8 Q16,3 20,8 Q24,3 28,8 Q32,4 34,10 Q38,16 34,26 Q34,40 28,52 Q24,56 20,52 Q16,56 12,52 Q6,40 6,26 Q2,16 6,10 Z',
  premolar: 'M9,10 Q14,3 20,8 Q26,3 31,10 Q35,18 31,28 Q31,42 26,52 Q20,57 14,52 Q9,42 9,28 Q5,18 9,10 Z',
  canine:   'M20,3 Q27,9 30,18 Q33,30 28,44 Q24,56 20,53 Q16,56 12,44 Q7,30 10,18 Q13,9 20,3 Z',
  incisor:  'M11,5 Q20,2 29,5 Q33,14 30,26 Q29,42 24,52 Q20,57 16,52 Q11,42 10,26 Q7,14 11,5 Z',
};
```

- [ ] **Step 2: Add the arch builder**

```javascript
// Build one row of teeth as inline SVG. `chart` is the {teeth:{}} map from the API.
function buildToothRowSvg(fdiList, chart, isLower) {
  const cellW = 44, cellH = 64, pad = 4;
  let cells = '';
  fdiList.forEach((fdi, i) => {
    const x = i * cellW + pad;
    const entry = (chart.teeth || {})[fdi];
    const fill = entry && entry.color ? entry.color
               : entry ? '#cbd5e1'          // legacy/unknown tint
               : 'transparent';             // healthy = outline only
    const stroke = entry ? '#334155' : '#94a3b8';
    const dot = entry && entry.has_plan
      ? `<circle cx="${x+34}" cy="6" r="4" fill="#7c3aed"><title>${t('has_plan','Has plan')}</title></circle>` : '';
    const warn = entry && entry.unpaid_balance > 0
      ? `<circle cx="${x+34}" cy="${cellH-8}" r="4" fill="#f59e0b"><title>${t('unpaid','Unpaid')}: ₪ ${entry.unpaid_balance.toFixed(2)}</title></circle>` : '';
    const label = `<text x="${x+20}" y="${isLower ? cellH-1 : 10}" text-anchor="middle" class="tooth-num">${fdi}</text>`;
    const path = `<path d="${TOOTH_PATHS[fdiToothClass(fdi)]}" transform="translate(${x},${isLower ? 6 : 14}) ${isLower ? 'rotate(180 20 28)' : ''}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
    cells += `<g class="tooth" data-fdi="${fdi}" tabindex="0" role="button" aria-label="${t('tooth','Tooth')} ${fdi}">${path}${label}${dot}${warn}</g>`;
  });
  const w = fdiList.length * cellW + pad * 2;
  return `<svg viewBox="0 0 ${w} ${cellH}" width="100%" preserveAspectRatio="xMidYMid meet" class="tooth-row">${cells}</svg>`;
}

function buildToothArchSvg(chart) {
  return `<div class="arch arch-upper">${buildToothRowSvg(FDI_UPPER, chart, false)}</div>`
       + `<div class="arch arch-lower">${buildToothRowSvg(FDI_LOWER, chart, true)}</div>`;
}
```

- [ ] **Step 3: Add CSS**

In the portal's `<style>` block:

```css
.odontogram-card { padding: 16px; }
.arch { margin: 4px 0; }
.tooth { cursor: pointer; transition: filter var(--duration-fast, 150ms) ease; }
.tooth:hover, .tooth:focus-visible { filter: brightness(0.92) drop-shadow(0 1px 3px rgba(0,0,0,.25)); outline: none; }
.tooth-num { font-size: 9px; fill: var(--muted, #64748b); font-weight: 600; }
.tooth-legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 10px; }
.tooth-legend span { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }
.tooth-legend i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; border: 1px solid #334155; }
[dir="rtl"] .tooth-row { transform: scaleX(-1); }
[dir="rtl"] .tooth-num { transform: scaleX(-1); transform-origin: center; }
```

> The RTL rule mirrors the arch so quadrant 1 stays on the patient's right; the number labels are flipped back so they read normally.

- [ ] **Step 4: Manual verification (no wiring yet)**

In DevTools console: `document.body.insertAdjacentHTML('beforeend', '<div style="background:#fff;padding:20px">'+buildToothArchSvg({teeth:{'16':{color:'#ef4444',has_plan:true,unpaid_balance:150},'11':{color:'#3b82f6',unpaid_balance:0}}})+'</div>')`. Confirm: 16 is red with a purple plan dot + amber unpaid dot; 11 is blue; unmarked teeth are outline-only; lower row is flipped. Report a screenshot/observation.

- [ ] **Step 5: Commit**

```bash
git add templates.py
git commit -m "feat(web): tooth silhouettes + arch SVG builder + chart styles"
```

---

## Task 3: Render the odontogram card on the patient profile

**Files:** Modify `templates.py` (markup + JS)

- [ ] **Step 1: Add the card markup + render function**

Find the patient-profile view that contains `id="patient-followups-body"`. Insert an odontogram card **above** the follow-up section:

```html
<section class="card odontogram-card" id="odontogram-card" style="display:none;">
  <h3 data-i18n="odontogram">Tooth chart</h3>
  <div id="odontogram-arch"></div>
  <div class="tooth-legend" id="odontogram-legend"></div>
</section>
```

Add the render function (called whenever a patient profile opens — invoke it next to wherever `renderFollowupsRows`/the profile loader runs, passing the current patient id):

```javascript
let currentChartConditions = [];

async function renderOdontogram(patientId) {
  const card = document.getElementById('odontogram-card');
  if (!card) return;
  try {
    const resp = await fetch(`/api/patients/${patientId}/tooth-chart`);
    const chart = await resp.json();
    currentChartConditions = chart.conditions || [];
    document.getElementById('odontogram-arch').innerHTML = buildToothArchSvg(chart);
    document.getElementById('odontogram-legend').innerHTML = (chart.conditions || [])
      .map(c => `<span><i style="background:${c.color}"></i>${(currentLang==='ar' && c.name_ar) ? c.name_ar : c.name}</span>`)
      .join('');
    card.style.display = '';
    document.querySelectorAll('#odontogram-arch .tooth').forEach(el => {
      el.addEventListener('click', () => openToothPopup(patientId, el.dataset.fdi, chart));
      el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openToothPopup(patientId, el.dataset.fdi, chart); } });
    });
  } catch (e) {
    card.style.display = 'none';  // backend not present / older server — degrade silently
  }
}
```

> `currentLang` is the portal's existing language variable (used elsewhere for i18n). If it's named differently, use the existing one. `openToothPopup` is defined in Task 4 — until then it can be a `function openToothPopup(){}` stub so the page doesn't error.

- [ ] **Step 2: Wire the call into the profile loader**

Wherever the patient profile is populated (the function that fills `#patient-followups-body`), add `renderOdontogram(patientId);` after the follow-ups render, using that function's patient id.

- [ ] **Step 3: Manual verification**

With Track A running and at least one patient who has a follow-up with `tooth_no='16'`: open that patient's profile → the Tooth chart card appears, tooth 16 shows the legacy tint + (if unpaid) an amber dot, the legend lists the Core 8. Report observation.

- [ ] **Step 4: Commit**

```bash
git add templates.py
git commit -m "feat(web): render odontogram card on patient profile"
```

---

## Task 4: Tap-tooth popup — set condition · log treatment · add to plan

**Files:** Modify `templates.py` (markup + JS)

- [ ] **Step 1: Add a popup container**

Add once near the other modals:

```html
<div id="tooth-popup" class="modal" style="display:none;">
  <div class="modal-content" style="max-width:360px;">
    <h3 id="tooth-popup-title">—</h3>
    <div class="form-group">
      <label data-i18n="condition">Condition</label>
      <select id="tooth-popup-condition"></select>
    </div>
    <div class="form-group">
      <label data-i18n="note">Note</label>
      <input type="text" id="tooth-popup-note" autocomplete="off">
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
      <button class="btn btn-primary" id="tooth-popup-save" data-i18n="save">Save</button>
      <button class="btn" id="tooth-popup-log" data-i18n="log_treatment">+ Log treatment</button>
      <button class="btn" id="tooth-popup-plan" data-i18n="add_to_plan">+ Add to plan</button>
      <button class="btn btn-ghost" id="tooth-popup-close" data-i18n="cancel">Cancel</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Add the popup logic**

```javascript
let _popupPatientId = null, _popupFdi = null;

function openToothPopup(patientId, fdi, chart) {
  _popupPatientId = patientId; _popupFdi = fdi;
  const entry = (chart.teeth || {})[fdi] || {};
  document.getElementById('tooth-popup-title').textContent = `${t('tooth','Tooth')} ${fdi}`;
  const sel = document.getElementById('tooth-popup-condition');
  // First option = Healthy/clear (sends null).
  sel.innerHTML = `<option value="">${t('healthy','Healthy')}</option>` +
    currentChartConditions
      .filter(c => c.name !== 'Healthy')
      .map(c => `<option value="${c.id}">${(currentLang==='ar' && c.name_ar) ? c.name_ar : c.name}</option>`)
      .join('');
  sel.value = entry.condition_id ? String(entry.condition_id) : '';
  document.getElementById('tooth-popup-note').value = entry.note || '';
  document.getElementById('tooth-popup').style.display = 'flex';
}

function closeToothPopup() { document.getElementById('tooth-popup').style.display = 'none'; }

document.getElementById('tooth-popup-close').addEventListener('click', closeToothPopup);

document.getElementById('tooth-popup-save').addEventListener('click', async () => {
  const condVal = document.getElementById('tooth-popup-condition').value;
  await fetch(`/api/patients/${_popupPatientId}/tooth-chart`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      tooth_no: _popupFdi,
      condition_id: condVal ? parseInt(condVal, 10) : null,   // '' → null = clear to healthy
      note: document.getElementById('tooth-popup-note').value || null,
    }),
  });
  closeToothPopup();
  renderOdontogram(_popupPatientId);
});

document.getElementById('tooth-popup-log').addEventListener('click', () => {
  closeToothPopup();
  openFollowupFormPrefilledTooth(_popupPatientId, _popupFdi);   // Task 5
});

document.getElementById('tooth-popup-plan').addEventListener('click', () => {
  closeToothPopup();
  addToothToPlan(_popupPatientId, _popupFdi);                    // Task 6
});
```

> `openFollowupFormPrefilledTooth` and `addToothToPlan` are defined in Tasks 5‑6; stub them as no-ops now so the page doesn't error.

- [ ] **Step 3: Manual verification**

Open a patient → click tooth 16 → popup shows, condition dropdown lists the catalog (Arabic labels when language = ع), current condition pre-selected. Pick "Crown" → Save → the tooth turns purple. Pick "Healthy" → Save → the tooth returns to outline-only. Report observation.

- [ ] **Step 4: Commit**

```bash
git add templates.py
git commit -m "feat(web): tap-tooth popup with set-condition save"
```

---

## Task 5: "+ Log treatment" → open follow-up Add form with tooth pre-filled

**Files:** Modify `templates.py` (JS)

- [ ] **Step 1: Read how the follow-up Add form opens**

Find the function that opens the follow-up Add modal (search around `id="followup-tooth-no"` / the form at `~5590`). Note the function name that shows it and how it resets fields.

- [ ] **Step 2: Implement the prefill helper**

```javascript
function openFollowupFormPrefilledTooth(patientId, fdi) {
  openFollowupForm(patientId);                 // the existing opener (use its real name)
  const el = document.getElementById('followup-tooth-no');
  if (el) el.value = fdi;
  const proc = document.getElementById('followup-procedure-id');
  if (proc) proc.focus();
}
```

> Use the existing follow-up-opener function name discovered in Step 1. The money/discount/ledger/invoice path is entirely unchanged — this only pre-sets the tooth field and moves focus to the procedure picker.

- [ ] **Step 3: Manual verification**

Click tooth 26 → "+ Log treatment" → the follow-up Add form opens with the tooth field showing `26`. Fill price/payment, save → the follow-up sheet gets the row, and re-opening the chart shows tooth 26 with an unpaid dot if a balance remains. Report observation.

- [ ] **Step 4: Commit**

```bash
git add templates.py
git commit -m "feat(web): + Log treatment opens follow-up form with tooth prefilled"
```

---

## Task 6: "+ Add to plan" → attach tooth to a treatment plan

**Files:** Modify `templates.py` (JS)

- [ ] **Step 1: Implement add-to-plan**

Minimal, dependency-free flow: list the patient's existing plans, let the user pick one or create a new one, then PUT/POST with the tooth added to its `teeth` array.

```javascript
async function addToothToPlan(patientId, fdi) {
  const plans = (await (await fetch('/api/treatment-plans')).json())
    .filter(p => p.patient_id === patientId);
  let choice = '';
  if (plans.length) {
    const menu = plans.map((p, i) => `${i + 1}. ${p.plan_name} [${(p.teeth || []).join(', ')}]`).join('\n');
    choice = prompt(`${t('add_to_plan','+ Add to plan')} — ${t('tooth','Tooth')} ${fdi}\n\n${menu}\n\n${t('plan_pick_hint','Enter a number, or a new plan name:')}`);
  } else {
    choice = prompt(`${t('plan_new_name','New plan name:')}`, `${t('plan','Plan')} ${fdi}`);
  }
  if (!choice) return;

  const asIndex = parseInt(choice, 10);
  if (plans.length && asIndex >= 1 && asIndex <= plans.length && String(asIndex) === choice.trim()) {
    const plan = plans[asIndex - 1];
    const teeth = Array.from(new Set([...(plan.teeth || []), fdi]));
    await fetch(`/api/treatment-plans/${plan.id}`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ plan_name: plan.plan_name, goals: plan.goals, estimated_cost: plan.estimated_cost,
                             status: plan.status, start_date: plan.start_date, end_date: plan.end_date,
                             notes: plan.notes, teeth }),
    });
  } else {
    await fetch('/api/treatment-plans', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ patient_id: patientId, plan_name: choice.trim(), teeth: [fdi] }),
    });
  }
  renderOdontogram(patientId);
  if (typeof renderTreatmentPlans === 'function') renderTreatmentPlans(patientId);  // refresh plans tab if present
}
```

> `prompt()` is intentionally low-ceremony for v1 (matches the repo's pragmatic inline-JS style); a richer picker can replace it later. The PUT echoes the plan's existing fields so the server's `plan_name`-required validation passes and only `teeth` changes.

- [ ] **Step 2: Manual verification**

Click tooth 36 → "+ Add to plan" → create "Upper crowns" → re-open chart: tooth 36 shows the purple plan dot. Click tooth 46 → "+ Add to plan" → pick the existing "Upper crowns" by number → 46 also shows the dot, and the plan's `teeth` now lists both. Report observation.

- [ ] **Step 3: Commit**

```bash
git add templates.py
git commit -m "feat(web): + Add to plan attaches tooth to a (multi-tooth) plan"
```

---

## Task 7: Tooth-condition admin under Administration

**Files:** Modify `templates.py` (markup + JS), mirroring `renderProcedureCatalogTable()` (`~3652`)

- [ ] **Step 1: Read the procedure-catalog admin to mirror it**

Read `templates.py:3652‑3700` (`renderProcedureCatalogTable`) and the markup at `~1887‑1894` to copy the table + add-form pattern exactly.

- [ ] **Step 2: Add the admin card markup**

In the Administration tab, beside the procedure-catalog card:

```html
<div class="card">
  <h3 data-i18n="tooth_conditions">Tooth conditions</h3>
  <div id="tooth-conditions-table"></div>
  <div class="form-row" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">
    <input type="text" id="tc-name" placeholder="Name">
    <input type="text" id="tc-name-ar" placeholder="الاسم">
    <input type="color" id="tc-color" value="#9ca3af">
    <input type="number" id="tc-sort" placeholder="#" style="width:64px;">
    <button class="btn btn-primary" id="tc-add" data-i18n="add">Add</button>
  </div>
</div>
```

- [ ] **Step 3: Add the admin CRUD JS**

```javascript
async function renderToothConditionsTable() {
  const wrap = document.getElementById('tooth-conditions-table');
  if (!wrap) return;
  const rows = await (await fetch('/api/tooth-conditions?all=1')).json();
  wrap.innerHTML = `<table class="data-table"><thead><tr>
      <th>${t('color','Color')}</th><th>${t('name','Name')}</th><th>${t('name_ar','Arabic')}</th>
      <th>#</th><th></th></tr></thead><tbody>` +
    rows.map(c => `<tr style="${c.active ? '' : 'opacity:.5;'}">
      <td><i style="display:inline-block;width:16px;height:16px;border-radius:3px;background:${c.color};border:1px solid #334155;"></i></td>
      <td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.name_ar || '')}</td><td>${c.sort_order}</td>
      <td>${c.active ? `<button class="btn btn-ghost" onclick="deleteToothCondition(${c.id})">${t('deactivate','Deactivate')}</button>` : ''}</td>
    </tr>`).join('') + '</tbody></table>';
}

async function addToothCondition() {
  const name = document.getElementById('tc-name').value.trim();
  if (!name) return;
  await fetch('/api/tooth-conditions', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name, name_ar: document.getElementById('tc-name-ar').value.trim() || null,
      color: document.getElementById('tc-color').value,
      sort_order: parseInt(document.getElementById('tc-sort').value, 10) || 0,
    }),
  });
  document.getElementById('tc-name').value = '';
  document.getElementById('tc-name-ar').value = '';
  renderToothConditionsTable();
}

async function deleteToothCondition(id) {
  await fetch(`/api/tooth-conditions/${id}`, { method: 'DELETE' });
  renderToothConditionsTable();
}

document.getElementById('tc-add')?.addEventListener('click', addToothCondition);
```

> `escapeHtml` already exists in the portal (used by the invoice escaping). Reuse it; do not define a second one. Call `renderToothConditionsTable()` when the Administration tab opens (next to the existing `renderProcedureCatalogTable()` call site).

- [ ] **Step 4: Manual verification**

Administration tab → Tooth conditions table lists the Core 8 with swatches. Add "Veneer" (green) → appears. Deactivate "Implant" → row dims, and it disappears from the tap-popup condition dropdown on the patient chart. Report observation.

- [ ] **Step 5: Commit**

```bash
git add templates.py
git commit -m "feat(web): tooth-condition admin under Administration"
```

---

## Task 8: i18n keys (EN + AR)

**Files:** Modify `templates.py` (`translations` EN `~2639`, AR `~3135`)

- [ ] **Step 1: Add the new keys to both blocks**

EN block:

```javascript
                odontogram: 'Tooth chart',
                tooth: 'Tooth',
                condition: 'Condition',
                tooth_conditions: 'Tooth conditions',
                healthy: 'Healthy',
                has_plan: 'Has plan',
                unpaid: 'Unpaid',
                log_treatment: '+ Log treatment',
                add_to_plan: '+ Add to plan',
                deactivate: 'Deactivate',
                name_ar: 'Arabic name',
                plan_pick_hint: 'Enter a number, or a new plan name:',
                plan_new_name: 'New plan name:',
```

AR block (`~3135`):

```javascript
                odontogram: 'مخطط الأسنان',
                tooth: 'سن',
                condition: 'الحالة',
                tooth_conditions: 'حالات الأسنان',
                healthy: 'سليم',
                has_plan: 'ضمن خطة',
                unpaid: 'غير مدفوع',
                log_treatment: '+ تسجيل علاج',
                add_to_plan: '+ إضافة إلى خطة',
                deactivate: 'إلغاء التفعيل',
                name_ar: 'الاسم بالعربية',
                plan_pick_hint: 'أدخل رقمًا، أو اسم خطة جديدة:',
                plan_new_name: 'اسم الخطة الجديدة:',
```

> Reuse existing keys where present (`name`, `note`, `save`, `cancel`, `add`, `color`, `price`, `plan`). Only add keys not already defined — search each key before adding to avoid duplicate-key shadowing.

- [ ] **Step 2: Manual verification**

Toggle language to ع → the card title reads "مخطط الأسنان", the legend + popup show Arabic condition names, the arch mirrors (quadrant 1 on the patient's right), tooth numbers still read left-to-right. Toggle back to EN. Report observation.

- [ ] **Step 3: Commit**

```bash
git add templates.py
git commit -m "feat(web): EN/AR i18n for the odontogram"
```

---

## Task 9: Visual polish + cross-cutting verification

**Files:** Modify `templates.py` (CSS/SVG refinement only)

- [ ] **Step 1: Refine the tooth silhouettes**

Open a patient chart in both light and dark theme. Adjust `TOOTH_PATHS` and CSS so molars read as molars, canines as pointed, incisors as blades — per the design-quality bar (intentional, not generic). Keep animations on `transform`/`filter`/`opacity` only.

- [ ] **Step 2: Full manual pass (report honestly)**

- [ ] New patient → all 32 teeth render healthy (outline), no badges.
- [ ] Set conditions across quadrants → colors correct, legend matches.
- [ ] Log a treatment from a tooth → ledger row created, unpaid dot appears.
- [ ] Add two teeth to one plan → both show the plan dot; deleting the plan clears both.
- [ ] Deactivate a condition → drops out of the picker; chart teeth using it render neutral.
- [ ] Light + dark theme both look intentional; RTL mirrors correctly.
- [ ] No console errors; on an old server without Track A, the card hides gracefully.

- [ ] **Step 3: Commit**

```bash
git add templates.py
git commit -m "polish(web): tooth silhouettes + light/dark + RTL pass"
```

---

## Self-Review (completed during planning)

- **Spec coverage (desktop section):** SVG arch of realistic silhouettes (Tasks 2,9) · tap popup with condition/log-treatment/add-to-plan/note (Tasks 4‑6) · plan/unpaid badges from the computed GET (Tasks 2‑3) · conditions admin mirroring the procedure catalog (Task 7) · EN/AR + RTL (Task 8, Task 2 CSS). All covered.
- **Contract consistency:** the chart GET keys consumed here (`teeth[fdi].color/condition_id/condition_name/note/source/has_plan/unpaid_balance`, `conditions[].{id,name,name_ar,color}`) exactly match Track A Task 8.
- **Placeholder scan:** complete code in every code step. The two cross-task references (`openFollowupForm`, the profile-loader function, `currentLang`, `escapeHtml`) are explicitly flagged as *existing* portal symbols to locate and reuse rather than invent — their real names live in `templates.py` and must be confirmed at the anchors given, not guessed.
- **Testing reality:** inline JS isn't unit-tested in this repo; each task carries explicit manual verification, consistent with the percentage-discount feature. This is stated honestly rather than fabricating JS unit tests.
