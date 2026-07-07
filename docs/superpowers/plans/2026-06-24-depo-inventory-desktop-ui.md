# Depo (Inventory) — Desktop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the desktop ("Depo") inventory UI in `templates.py` — a new top-level **Depo** tab (item list, stock value, low-stock/expiring badges), item editor, stock actions (Add stock / Adjust / Write-off), a materials sub-panel on the Catalog editor, follow-up "issued from stock" override rows, and a basic report — all consuming the inventory API the engine plan already shipped.

**Architecture:** Pure frontend. The engine + REST API (`/api/inventory/*`) and follow-up auto-deduct already landed on `feat/depo-inventory` (tip `b984dc0`); this plan adds **no backend**. The UI follows the app's established inline-template patterns: a `tab-content` panel toggled by `switchTab`, JS `fetch`→cache→render, the `translations.en`/`translations.ar` maps + `t(key, fallback)` for bilingual copy, and existing components (`.section-card`, `.stat-card`, `.form-panel`, `.table-container`, `.btn`, `.badge-*`, `.modal`/`closeModal`, `showToast`).

**Tech Stack:** Python (Flask serves the template), inline HTML/CSS/JS inside the `HTML_TEMPLATE` Python string in `templates.py`, pytest for template-content regression, Playwright (MCP) + `node --check` for behavioral/JS-integrity verification. No new dependencies.

**Scope of THIS plan:** desktop UI only. **Out of scope (separate follow-on plan):** the Flutter read-only Depo screen (`clinic_mobile_app/`).

## Global Constraints

- **Consumes existing endpoints only** (engine plan `b984dc0`): `GET/POST /api/inventory/items`, `PUT /api/inventory/items/<id>`, `POST .../restock`, `POST .../adjust`, `POST .../writeoff`, `GET /api/inventory/report`, `GET/POST/DELETE /api/inventory/procedures/<id>/materials`, and the follow-up POST/PUT accepting `materials: [{item_id, qty}]` + returning `stock_warnings`. Do not add or change backend routes.
- **Placement:** a new **top-level `Depo` nav-tab** (EN `Depo`, AR `مخزن`) in the **Management** nav group, inserted between the `treatments` (Catalog) and `support` (Settings) tabs. Tab content id = `depo`.
- **Bilingual EN/AR is mandatory** for every new string. Three supported mechanisms (use the one that matches surrounding code): static text → `data-en="…" data-ar="…"`; static text with a translation key → `data-i18n="key"` + add `key` to **both** `translations.en` and `translations.ar`; JS-built strings → `t('key','English fallback')` + add the key to both maps.
- **JS escaping trap (CRITICAL — see project memory `reference_templates_js_escaping`):** `HTML_TEMPLATE` is a *normal* Python triple-quoted string, NOT a raw string. A literal `\n`/`\t`/`\d` you type inside inline JS is collapsed by Python *before* the browser sees it, which silently breaks the entire `<script>`. Never write a bare backslash-escape in added JS. Use template literals / DOM APIs instead of `'\n'`; if a regex is unavoidable write `\\d` (double-backslash). Every task that adds JS ends with a `node --check` parse of the extracted script.
- **Design system:** reuse existing classes; do not invent new visual primitives. "Glass for chrome, solid for data." Low-stock badge = `.badge-warning`; negative/out-of-stock = `.badge-danger`; healthy = `.badge-success`; expiring-soon = `.badge-warning`. Buttons: primary action `.btn .btn-primary`, corrective `.btn .btn-warning`, destructive `.btn .btn-danger`.
- **Insight-only money:** show `cost_per_unit` and on-hand value as *information* only. Never present material cost as affecting clinic profit, and never display it inside the follow-up billing math (the billing preview must stay unchanged).
- **Packs-remaining is display-only:** `packs_remaining` comes from the API (`quantity / pack_size`); show it next to on-hand, never as an editable field.
- **Never block the workflow:** stock warnings surface via `showToast(..., 'warning')`; a low/negative item never prevents saving a follow-up (the backend already guarantees this — the UI must not add a blocking check).
- **Style:** match the file's existing 4-space-indented inline JS, semicolon style, and `const`/`let` usage. Small commits, one per task.

## File Structure

| File | Responsibility |
|---|---|
| `templates.py` (**modify**) | All desktop UI: the Depo nav-tab + `#depo` panel, item list render, item editor, stock-action modals, the Catalog materials sub-panel, follow-up override rows, the report panel, and all new translation keys. |
| `tests/test_depo_ui.py` (**create**) | Template-content regression: asserts each feature's DOM ids, JS function names, and bilingual keys are present in `HTML_TEMPLATE`, and that both language maps stay balanced. Cheap, always-run guard against missing wiring / dropped AR strings. |

**Anchors (verified against `feat/depo-inventory` tip `b984dc0`; re-grep before editing — line numbers shift as you insert):**
- Nav group "Management" + `support` tab button: search `data-tab="support"` (the Depo button goes immediately *before* this button; the `<div class="nav-group-label" data-i18n="management">` precedes the `treatments` button).
- Tab panels container: search `<div class="content">`; the `treatments` panel is `<div id="treatments" class="tab-content">`, and the Settings/`support` panel follows the others. Insert `<div id="depo" class="tab-content">` as a sibling.
- Catalog procedure editor: search `id="catalog-subtab-procedure"` and `id="procedures-body"` (the materials sub-panel attaches inside the `treatments` panel, after the procedures table `section-card`).
- Procedure render: `loadTreatmentProcedures()` (search `async function loadTreatmentProcedures`) + `getProcedureById` + `updateFollowupProcedureUi` (search `function updateFollowupProcedureUi`).
- Tab switch / i18n hooks: `function switchTab(` and `function applyLanguage(` — both have an `if (tabName === …)/(activeTab === …)` chain to extend.
- Follow-up form (a JS template literal): search `id="patient-followup-form"`; its submit handler: search `document.getElementById('patient-followup-form').addEventListener('submit'` and the `JSON.stringify(data)` line inside it.
- Translations: `const translations = {` then `en: {` (search `const translations = {`) and `ar: {` (search the `ar: {` that follows); `function t(key, fallback = '')`.
- Toast: `function showToast(message, type = 'info', opts = {})`.
- Modals: existing modals use `<div id="…-modal" class="modal">` + `closeModal('…-modal')`.

---

### Task 1: Depo nav-tab + section shell + item-list render

**Files:**
- Modify: `templates.py` (nav button; `#depo` panel; `loadDepoSection`/`loadInventoryItems`/`renderInventoryItems`; hook `switchTab` + `applyLanguage`; translation keys)
- Test: `tests/test_depo_ui.py` (**create**)

**Interfaces:**
- Produces: tab id `depo`; JS globals `inventoryItemsCache` (array) and functions `loadDepoSection()`, `loadInventoryItems()`, `renderInventoryItems()`; DOM ids `depo-items-body` (tbody), `depo-item-count`, `depo-stock-value`. Consumed by Tasks 2, 3, 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_depo_ui.py
import re
import templates

HTML = templates.HTML_TEMPLATE


def _lang_map(name):
    """Return the raw text of translations.<name> = { ... } block for key checks."""
    m = re.search(name + r':\s*\{', HTML)
    assert m, f'translations.{name} map not found'
    start = m.end()
    depth = 1
    i = start
    while i < len(HTML) and depth:
        if HTML[i] == '{':
            depth += 1
        elif HTML[i] == '}':
            depth -= 1
        i += 1
    return HTML[start:i]


def test_depo_nav_tab_and_panel_present():
    assert 'data-tab="depo"' in HTML
    assert "switchTab('depo'" in HTML
    assert 'id="depo"' in HTML and 'class="tab-content"' in HTML
    assert 'id="depo-items-body"' in HTML


def test_depo_list_render_wired():
    assert 'function loadDepoSection' in HTML
    assert 'function renderInventoryItems' in HTML
    assert "fetch('/api/inventory/items')" in HTML or 'fetch(`/api/inventory/items' in HTML
    # lazy-load + language-refresh hooks
    assert "tabName === 'depo'" in HTML
    assert "activeTab === 'depo'" in HTML


def test_depo_core_strings_are_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('depo_title', 'on_hand', 'packs_remaining', 'low_stock', 'stock_value'):
        assert f'{key}:' in en, f'missing EN key {key}'
        assert f'{key}:' in ar, f'missing AR key {key}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_depo_ui.py -q`
Expected: FAIL — anchors/keys not present yet.

- [ ] **Step 3: Add the nav-tab button**

Find the `support` nav button (search `data-tab="support"`). Insert immediately **before** it:

```html
            <button class="nav-tab" data-tab="depo" onclick="switchTab('depo', this)">
                <span class="tab-icon"><svg class="ic"><use href="#i-package"/></svg></span>
                <span data-en="Depo" data-ar="مخزن">Depo</span>
            </button>
```

> Icon note: if `#i-package` is not in the inline sprite, reuse an existing glyph that *is* present — `#i-folders` is safe (search `href="#i-folders"`). Do not add a CDN icon.

- [ ] **Step 4: Add the `#depo` tab panel**

Find the end of the `treatments` panel (the `<div id="treatments" class="tab-content">` … its matching close before the next `tab-content`). Insert this sibling panel right after it:

```html
            <!-- Depo Tab -->
            <div id="depo" class="tab-content">
                <div class="screen-shell">
                    <div class="section-card">
                        <div class="section-card-header">
                            <div>
                                <h2 data-i18n="depo_title">Depo</h2>
                                <p data-i18n="depo_summary">Stock items, on-hand levels, and low-stock alerts.</p>
                            </div>
                            <div class="toolbar-row">
                                <button class="btn btn-primary" type="button" onclick="openInventoryItemEditor()" data-i18n="add_item">+ Add Item</button>
                            </div>
                        </div>
                        <div class="admin-overview-cards">
                            <div class="stat-card stat-card-teal">
                                <span class="stat-icon">📦</span>
                                <h3 id="depo-item-count">0</h3>
                                <p data-i18n="items_in_stock">Items in stock</p>
                            </div>
                            <div class="stat-card">
                                <span class="stat-icon">💰</span>
                                <h3 id="depo-stock-value">0</h3>
                                <p data-i18n="stock_value">Stock value</p>
                            </div>
                        </div>
                    </div>
                    <div class="section-card">
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th data-i18n="item">Item</th>
                                        <th class="numeric-cell" data-i18n="on_hand">On hand</th>
                                        <th class="numeric-cell" data-i18n="packs_remaining">Packs</th>
                                        <th class="center-cell" data-i18n="status">Status</th>
                                        <th class="actions-cell" data-i18n="actions">Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="depo-items-body"><tr><td colspan="5" data-i18n="no_data">No data</td></tr></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
```

- [ ] **Step 5: Add the render JS**

Add near `loadTreatmentProcedures` (search `async function loadTreatmentProcedures`). Note the escaping trap — this uses template literals only, no bare `\n`:

```javascript
        let inventoryItemsCache = [];

        async function loadInventoryItems() {
            try {
                const res = await fetch('/api/inventory/items');
                inventoryItemsCache = await res.json();
                if (!Array.isArray(inventoryItemsCache)) inventoryItemsCache = [];
            } catch (_) {
                inventoryItemsCache = [];
            }
            return inventoryItemsCache;
        }

        function inventoryStatusBadge(item) {
            const qty = Number(item.quantity) || 0;
            const threshold = Number(item.low_stock_threshold) || 0;
            if (qty < 0) return `<span class="badge badge-danger">${t('negative','Negative')}</span>`;
            if (qty <= threshold) return `<span class="badge badge-warning">${t('low_stock','Low stock')}</span>`;
            return `<span class="badge badge-success">${t('in_stock','In stock')}</span>`;
        }

        function renderInventoryItems() {
            const body = document.getElementById('depo-items-body');
            if (!body) return;
            const items = inventoryItemsCache;
            if (!items.length) {
                body.innerHTML = `<tr><td colspan="5">${t('no_data','No data')}</td></tr>`;
            } else {
                body.innerHTML = items.map(it => {
                    const qty = Number(it.quantity) || 0;
                    const packs = (it.packs_remaining == null) ? '—' : (Math.round(it.packs_remaining * 100) / 100);
                    const unit = it.base_unit ? ` <small style="color:var(--muted)">${it.base_unit}</small>` : '';
                    return `<tr>
                        <td>${escapeHtml(it.name || '')}</td>
                        <td class="numeric-cell">${qty}${unit}</td>
                        <td class="numeric-cell">${packs}</td>
                        <td class="center-cell">${inventoryStatusBadge(it)}</td>
                        <td class="actions-cell">
                            <button class="btn btn-sm" onclick="openInventoryItemEditor(${it.id})" data-i18n="edit">Edit</button>
                            <button class="btn btn-sm btn-primary" onclick="openRestockModal(${it.id})" data-i18n="add_stock">Add stock</button>
                        </td>
                    </tr>`;
                }).join('');
            }
            const count = document.getElementById('depo-item-count');
            if (count) count.textContent = items.length;
            const value = document.getElementById('depo-stock-value');
            if (value) {
                const total = items.reduce((s, it) =>
                    s + (Number(it.quantity) || 0) * (Number(it.cost_per_unit) || 0), 0);
                value.textContent = '₪ ' + total.toFixed(2);
            }
        }

        async function loadDepoSection() {
            await loadInventoryItems();
            renderInventoryItems();
        }
```

> Reuse, don't redefine: `escapeHtml` (templates.py ~`:4470`), `parseCurrency` (~`:4480`), and `t` already exist — confirmed present. **There is no `formatCurrency` helper:** money is rendered as `'₪ ' + n.toFixed(2)` (the codebase idiom is `₪ ${parseCurrency(v).toFixed(2)}`). The `openInventoryItemEditor` / `openRestockModal` handlers are defined in Tasks 2 & 3 — the buttons reference them now and become live then.

- [ ] **Step 6: Hook lazy-load + language refresh**

In `switchTab` (search `function switchTab(`), add to the load chain (before the closing `}` of the `if/else if` ladder):

```javascript
            else if (tabName === 'depo')         loadDepoSection();
```

In `applyLanguage` (search `const activeTab = document.querySelector('.tab-content.active')?.id;`), add to that ladder:

```javascript
            else if (activeTab === 'depo') loadDepoSection();
```

- [ ] **Step 7: Add translation keys**

In `translations.en` (search `const translations = {` → `en: {`) add:

```javascript
                depo_title: 'Depo',
                depo_summary: 'Stock items, on-hand levels, and low-stock alerts.',
                add_item: '+ Add Item',
                items_in_stock: 'Items in stock',
                stock_value: 'Stock value',
                item: 'Item',
                on_hand: 'On hand',
                packs_remaining: 'Packs',
                in_stock: 'In stock',
                low_stock: 'Low stock',
                negative: 'Negative',
                add_stock: 'Add stock',
```

In `translations.ar` (the `ar: {` block) add the parallel keys:

```javascript
                depo_title: 'مخزن',
                depo_summary: 'مواد المخزون ومستويات التوفر وتنبيهات النقص.',
                add_item: '+ إضافة مادة',
                items_in_stock: 'مواد في المخزون',
                stock_value: 'قيمة المخزون',
                item: 'المادة',
                on_hand: 'المتوفر',
                packs_remaining: 'العبوات',
                in_stock: 'متوفر',
                low_stock: 'مخزون منخفض',
                negative: 'سالب',
                add_stock: 'إضافة مخزون',
```

- [ ] **Step 8: Run tests + integrity check**

Run: `python -m pytest tests/test_depo_ui.py -q` → Expected: PASS.
Run: `python -c "import templates; print('ok', len(templates.HTML_TEMPLATE))"` → Expected: prints `ok …` (no SyntaxError).
Run the JS parse sweep (extracts the inline script and checks it parses — catches the escaping trap):

```bash
python - <<'PY'
import re, subprocess, tempfile, os, templates
html = templates.HTML_TEMPLATE
scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
blob = "\n".join(s for s in scripts if 'function' in s)
f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
f.write(blob); f.close()
print(subprocess.run(['node', '--check', f.name], capture_output=True, text=True).stderr or 'JS OK')
os.unlink(f.name)
PY
```
Expected: `JS OK`.

- [ ] **Step 9: Commit**

```bash
git add templates.py tests/test_depo_ui.py
git commit -m "feat(depo-ui): Depo tab + item-list render (on-hand, packs, low-stock, value)"
```

---

### Task 2: Item editor (create / edit / deactivate)

**Files:**
- Modify: `templates.py` (item editor modal + `openInventoryItemEditor`, `saveInventoryItem`, `deactivateInventoryItem`; translation keys)
- Test: `tests/test_depo_ui.py`

**Interfaces:**
- Consumes: `inventoryItemsCache`, `loadDepoSection` (Task 1).
- Produces: `openInventoryItemEditor(id?)`, `saveInventoryItem(event)`, `deactivateInventoryItem(id)`; modal id `depo-item-modal`. Consumed by the list buttons (Task 1) and Task 3 (after stock actions reload).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_depo_ui.py
def test_item_editor_modal_and_handlers():
    assert 'id="depo-item-modal"' in HTML
    assert 'function openInventoryItemEditor' in HTML
    assert 'function saveInventoryItem' in HTML
    assert 'function deactivateInventoryItem' in HTML
    # all spec'd item fields have inputs
    for fid in ('depo-item-name', 'depo-item-name-ar', 'depo-item-category',
                'depo-item-base-unit', 'depo-item-pack-unit', 'depo-item-pack-size',
                'depo-item-threshold', 'depo-item-reorder', 'depo-item-supplier',
                'depo-item-location', 'depo-item-track-expiry'):
        assert f'id="{fid}"' in HTML, f'missing field {fid}'
    # POST create / PUT edit
    assert "method: 'POST'" in HTML and "method: 'PUT'" in HTML


def test_item_editor_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('edit_item', 'track_expiry', 'reorder_qty', 'supplier', 'location', 'deactivate'):
        assert f'{key}:' in en and f'{key}:' in ar, f'missing bilingual key {key}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_depo_ui.py -q`
Expected: FAIL — modal/handlers absent.

- [ ] **Step 3: Add the item editor modal**

Add near the other modals (search for an existing `class="modal"` block, e.g. `id="edit-followup-modal"`, and place this beside it):

```html
    <div id="depo-item-modal" class="modal" onclick="if(event.target===this)closeModal('depo-item-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="depo-item-modal-title" data-i18n="add_item">Add Item</h3>
                <button type="button" class="modal-close" onclick="closeModal('depo-item-modal')">&times;</button>
            </div>
            <form id="depo-item-form" onsubmit="saveInventoryItem(event)">
                <input type="hidden" id="depo-item-id" value="">
                <div class="form-row">
                    <div class="form-group"><label data-i18n="item_name_required">Name *</label>
                        <input type="text" id="depo-item-name" required></div>
                    <div class="form-group"><label data-i18n="item_name_ar">Name (Arabic)</label>
                        <input type="text" id="depo-item-name-ar" dir="rtl"></div>
                </div>
                <div class="form-row-3">
                    <div class="form-group"><label data-i18n="category">Category</label>
                        <input type="text" id="depo-item-category"></div>
                    <div class="form-group"><label data-i18n="base_unit">Base unit</label>
                        <input type="text" id="depo-item-base-unit" placeholder="piece / carpule / ml"></div>
                    <div class="form-group"><label data-i18n="pack_unit">Pack unit</label>
                        <input type="text" id="depo-item-pack-unit" placeholder="box / bottle"></div>
                </div>
                <div class="form-row-3">
                    <div class="form-group"><label data-i18n="pack_size">Pack size</label>
                        <input type="number" step="any" id="depo-item-pack-size" value="1"></div>
                    <div class="form-group"><label data-i18n="low_stock_threshold">Low-stock threshold</label>
                        <input type="number" step="any" id="depo-item-threshold" value="0"></div>
                    <div class="form-group"><label data-i18n="reorder_qty">Reorder qty</label>
                        <input type="number" step="any" id="depo-item-reorder"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label data-i18n="supplier">Supplier</label>
                        <input type="text" id="depo-item-supplier"></div>
                    <div class="form-group"><label data-i18n="location">Location</label>
                        <input type="text" id="depo-item-location"></div>
                </div>
                <div class="toolbar-row">
                    <label style="display:flex; gap:8px; align-items:center; font-weight:600;">
                        <input type="checkbox" id="depo-item-track-expiry">
                        <span data-i18n="track_expiry">Track expiry</span>
                    </label>
                </div>
                <div class="toolbar-row" style="justify-content:space-between;">
                    <button class="btn btn-primary" type="submit" data-i18n="save">Save</button>
                    <button class="btn btn-danger" type="button" id="depo-item-deactivate-btn"
                            style="display:none;" onclick="deactivateInventoryItem()" data-i18n="deactivate">Deactivate</button>
                </div>
            </form>
        </div>
    </div>
```

- [ ] **Step 4: Add the editor JS**

Add after `loadDepoSection` (Task 1):

```javascript
        function openInventoryItemEditor(id) {
            const item = (id != null) ? inventoryItemsCache.find(x => x.id === id) : null;
            const setVal = (fid, v) => { const el = document.getElementById(fid); if (el) el.value = (v == null ? '' : v); };
            document.getElementById('depo-item-id').value = item ? item.id : '';
            setVal('depo-item-name', item && item.name);
            setVal('depo-item-name-ar', item && item.name_ar);
            setVal('depo-item-category', item && item.category);
            setVal('depo-item-base-unit', item ? (item.base_unit || 'piece') : 'piece');
            setVal('depo-item-pack-unit', item && item.pack_unit);
            setVal('depo-item-pack-size', item ? (item.pack_size != null ? item.pack_size : 1) : 1);
            setVal('depo-item-threshold', item ? (item.low_stock_threshold || 0) : 0);
            setVal('depo-item-reorder', item && item.reorder_qty);
            setVal('depo-item-supplier', item && item.supplier);
            setVal('depo-item-location', item && item.location);
            document.getElementById('depo-item-track-expiry').checked = Boolean(item && Number(item.track_expiry) === 1);
            document.getElementById('depo-item-modal-title').textContent =
                item ? t('edit_item','Edit Item') : t('add_item','Add Item');
            document.getElementById('depo-item-deactivate-btn').style.display = item ? '' : 'none';
            document.getElementById('depo-item-modal').classList.add('active');
        }

        async function saveInventoryItem(event) {
            event.preventDefault();
            const id = document.getElementById('depo-item-id').value;
            const numOrNull = (fid) => {
                const v = document.getElementById(fid).value;
                return v === '' ? null : Number(v);
            };
            const payload = {
                name: document.getElementById('depo-item-name').value.trim(),
                name_ar: document.getElementById('depo-item-name-ar').value.trim() || null,
                category: document.getElementById('depo-item-category').value.trim() || null,
                base_unit: document.getElementById('depo-item-base-unit').value.trim() || 'piece',
                pack_unit: document.getElementById('depo-item-pack-unit').value.trim() || null,
                pack_size: numOrNull('depo-item-pack-size'),
                low_stock_threshold: numOrNull('depo-item-threshold'),
                reorder_qty: numOrNull('depo-item-reorder'),
                supplier: document.getElementById('depo-item-supplier').value.trim() || null,
                location: document.getElementById('depo-item-location').value.trim() || null,
                track_expiry: document.getElementById('depo-item-track-expiry').checked,
            };
            if (!payload.name) { showToast(t('item_name_required','Name is required'), 'warning'); return; }
            const url = id ? `/api/inventory/items/${id}` : '/api/inventory/items';
            const res = await fetch(url, {
                method: id ? 'PUT' : 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const p = await res.json().catch(() => ({}));
                showToast(p.error || t('unable_save_item','Unable to save item.'), 'error');
                return;
            }
            closeModal('depo-item-modal');
            showToast(t('item_saved','Item saved.'), 'success');
            await loadDepoSection();
        }

        async function deactivateInventoryItem() {
            const id = document.getElementById('depo-item-id').value;
            if (!id) return;
            const res = await fetch(`/api/inventory/items/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({active: false}),
            });
            if (!res.ok) { showToast(t('unable_save_item','Unable to save item.'), 'error'); return; }
            closeModal('depo-item-modal');
            showToast(t('item_deactivated','Item deactivated.'), 'success');
            await loadDepoSection();
        }
```

> Modal mechanism (confirmed): the template has **no `openModal` helper**. Open a modal with `document.getElementById('<id>').classList.add('active')` and close with the existing `closeModal('<id>')` (templates.py ~`:5030`, which removes `.active`; Escape also closes any `.modal.active`). Every `open*Modal` handler in this plan uses `classList.add('active')`.

- [ ] **Step 5: Add translation keys**

Add to `translations.en` and `translations.ar` (parallel). EN:

```javascript
                edit_item: 'Edit Item',
                item_name_required: 'Name is required',
                item_name_ar: 'Name (Arabic)',
                base_unit: 'Base unit',
                pack_unit: 'Pack unit',
                pack_size: 'Pack size',
                low_stock_threshold: 'Low-stock threshold',
                reorder_qty: 'Reorder qty',
                supplier: 'Supplier',
                location: 'Location',
                track_expiry: 'Track expiry',
                deactivate: 'Deactivate',
                unable_save_item: 'Unable to save item.',
                item_saved: 'Item saved.',
                item_deactivated: 'Item deactivated.',
```

AR:

```javascript
                edit_item: 'تعديل المادة',
                item_name_required: 'الاسم مطلوب',
                item_name_ar: 'الاسم (بالعربية)',
                base_unit: 'الوحدة الأساسية',
                pack_unit: 'وحدة العبوة',
                pack_size: 'حجم العبوة',
                low_stock_threshold: 'حد المخزون المنخفض',
                reorder_qty: 'كمية إعادة الطلب',
                supplier: 'المورّد',
                location: 'الموقع',
                track_expiry: 'تتبّع الصلاحية',
                deactivate: 'إلغاء التفعيل',
                unable_save_item: 'تعذّر حفظ المادة.',
                item_saved: 'تم حفظ المادة.',
                item_deactivated: 'تم إلغاء تفعيل المادة.',
```

> `category` already exists in both maps (used by the catalog) — do not duplicate it; reuse the existing key.

- [ ] **Step 6: Run tests + integrity**

Run: `python -m pytest tests/test_depo_ui.py -q` → PASS.
Run the `python -c "import templates…"` + `node --check` sweep from Task 1 Step 8 → no errors.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_depo_ui.py
git commit -m "feat(depo-ui): item editor (create/edit/deactivate) with track-expiry"
```

---

### Task 3: Stock actions — Add stock / Adjust count / Write-off

**Files:**
- Modify: `templates.py` (three modals + `openRestockModal`/`submitRestock`, `openAdjustModal`/`submitAdjust`, `openWriteoffModal`/`submitWriteoff`; translation keys)
- Test: `tests/test_depo_ui.py`

**Interfaces:**
- Consumes: `inventoryItemsCache`, `loadDepoSection` (Task 1).
- Produces: `openRestockModal(id)`, `openAdjustModal(id)`, `openWriteoffModal(id)` and their `submit*` handlers; modal ids `depo-restock-modal`, `depo-adjust-modal`, `depo-writeoff-modal`. Restock/adjust/write-off buttons added to the list row's Actions.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_depo_ui.py
def test_stock_action_modals_and_handlers():
    for mid in ('depo-restock-modal', 'depo-adjust-modal', 'depo-writeoff-modal'):
        assert f'id="{mid}"' in HTML, f'missing {mid}'
    for fn in ('openRestockModal', 'submitRestock', 'openAdjustModal',
               'submitAdjust', 'openWriteoffModal', 'submitWriteoff'):
        assert f'function {fn}' in HTML, f'missing {fn}'
    assert '/restock' in HTML and '/adjust' in HTML and '/writeoff' in HTML
    # restock toggles expiry input only when the item tracks expiry
    assert 'depo-restock-expiry' in HTML


def test_stock_action_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('adjust_count', 'write_off', 'quantity', 'unit_cost', 'counted_qty', 'expiry_date'):
        assert f'{key}:' in en and f'{key}:' in ar, f'missing bilingual key {key}'
```

- [ ] **Step 2: Run to verify fail** — `python -m pytest tests/test_depo_ui.py -q` → FAIL.

- [ ] **Step 3: Add the three modals**

Place beside the item modal:

```html
    <div id="depo-restock-modal" class="modal" onclick="if(event.target===this)closeModal('depo-restock-modal')">
        <div class="modal-content">
            <div class="modal-header"><h3 data-i18n="add_stock">Add stock</h3>
                <button type="button" class="modal-close" onclick="closeModal('depo-restock-modal')">&times;</button></div>
            <form onsubmit="submitRestock(event)">
                <input type="hidden" id="depo-restock-id">
                <div class="form-row">
                    <div class="form-group"><label data-i18n="quantity">Quantity (base units)</label>
                        <input type="number" step="any" id="depo-restock-qty" required></div>
                    <div class="form-group"><label data-i18n="unit_cost">Unit cost</label>
                        <input type="number" step="any" id="depo-restock-cost" value="0"></div>
                </div>
                <div class="form-group" id="depo-restock-expiry-wrap" style="display:none;">
                    <label data-i18n="expiry_date">Expiry date</label>
                    <input type="date" id="depo-restock-expiry"></div>
                <div class="toolbar-row"><button class="btn btn-primary" type="submit" data-i18n="add_stock">Add stock</button></div>
            </form>
        </div>
    </div>
    <div id="depo-adjust-modal" class="modal" onclick="if(event.target===this)closeModal('depo-adjust-modal')">
        <div class="modal-content">
            <div class="modal-header"><h3 data-i18n="adjust_count">Adjust count</h3>
                <button type="button" class="modal-close" onclick="closeModal('depo-adjust-modal')">&times;</button></div>
            <form onsubmit="submitAdjust(event)">
                <input type="hidden" id="depo-adjust-id">
                <div class="form-group"><label data-i18n="counted_qty">Counted quantity</label>
                    <input type="number" step="any" id="depo-adjust-qty" required></div>
                <div class="form-group"><label data-i18n="note">Note</label>
                    <input type="text" id="depo-adjust-note"></div>
                <div class="toolbar-row"><button class="btn btn-warning" type="submit" data-i18n="adjust_count">Adjust count</button></div>
            </form>
        </div>
    </div>
    <div id="depo-writeoff-modal" class="modal" onclick="if(event.target===this)closeModal('depo-writeoff-modal')">
        <div class="modal-content">
            <div class="modal-header"><h3 data-i18n="write_off">Write-off</h3>
                <button type="button" class="modal-close" onclick="closeModal('depo-writeoff-modal')">&times;</button></div>
            <form onsubmit="submitWriteoff(event)">
                <input type="hidden" id="depo-writeoff-id">
                <div class="form-group"><label data-i18n="quantity">Quantity</label>
                    <input type="number" step="any" id="depo-writeoff-qty" required></div>
                <div class="form-group"><label data-i18n="note">Note</label>
                    <input type="text" id="depo-writeoff-note" placeholder="breakage / contamination / expired"></div>
                <div class="toolbar-row"><button class="btn btn-danger" type="submit" data-i18n="write_off">Write-off</button></div>
            </form>
        </div>
    </div>
```

- [ ] **Step 4: Add the handlers**

```javascript
        function openRestockModal(id) {
            const item = inventoryItemsCache.find(x => x.id === id);
            document.getElementById('depo-restock-id').value = id;
            document.getElementById('depo-restock-qty').value = '';
            document.getElementById('depo-restock-cost').value = item ? (item.cost_per_unit || 0) : 0;
            document.getElementById('depo-restock-expiry').value = '';
            document.getElementById('depo-restock-expiry-wrap').style.display =
                (item && Number(item.track_expiry) === 1) ? '' : 'none';
            document.getElementById('depo-restock-modal').classList.add('active');
        }

        function _stockWarnToast(res) {
            // The follow-up path returns stock_warnings; restock returns low_stock.
            if (res && res.low_stock) showToast(t('now_low_stock','Item is now at/below its low-stock level.'), 'warning');
        }

        async function submitRestock(event) {
            event.preventDefault();
            const id = document.getElementById('depo-restock-id').value;
            const payload = {
                base_qty: Number(document.getElementById('depo-restock-qty').value),
                unit_cost: Number(document.getElementById('depo-restock-cost').value),
                expiry_date: document.getElementById('depo-restock-expiry').value || null,
            };
            const res = await fetch(`/api/inventory/items/${id}/restock`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
            if (!res.ok) { const p = await res.json().catch(()=>({})); showToast(p.error || t('unable_restock','Unable to add stock.'), 'error'); return; }
            closeModal('depo-restock-modal');
            showToast(t('stock_added','Stock added.'), 'success');
            await loadDepoSection();
        }

        async function submitAdjust(event) {
            event.preventDefault();
            const id = document.getElementById('depo-adjust-id').value;
            const payload = {
                counted_qty: Number(document.getElementById('depo-adjust-qty').value),
                note: document.getElementById('depo-adjust-note').value || null};
            const res = await fetch(`/api/inventory/items/${id}/adjust`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
            if (!res.ok) { const p = await res.json().catch(()=>({})); showToast(p.error || t('unable_adjust','Unable to adjust.'), 'error'); return; }
            closeModal('depo-adjust-modal');
            showToast(t('count_adjusted','Count adjusted.'), 'success');
            await loadDepoSection();
        }
        function openAdjustModal(id) {
            const item = inventoryItemsCache.find(x => x.id === id);
            document.getElementById('depo-adjust-id').value = id;
            document.getElementById('depo-adjust-qty').value = item ? (item.quantity || 0) : 0;
            document.getElementById('depo-adjust-note').value = '';
            document.getElementById('depo-adjust-modal').classList.add('active');
        }

        async function submitWriteoff(event) {
            event.preventDefault();
            const id = document.getElementById('depo-writeoff-id').value;
            const payload = {
                qty: Number(document.getElementById('depo-writeoff-qty').value),
                note: document.getElementById('depo-writeoff-note').value || null};
            const res = await fetch(`/api/inventory/items/${id}/writeoff`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
            if (!res.ok) { const p = await res.json().catch(()=>({})); showToast(p.error || t('unable_writeoff','Unable to write off.'), 'error'); return; }
            closeModal('depo-writeoff-modal');
            showToast(t('written_off','Written off.'), 'success');
            await loadDepoSection();
        }
        function openWriteoffModal(id) {
            document.getElementById('depo-writeoff-id').value = id;
            document.getElementById('depo-writeoff-qty').value = '';
            document.getElementById('depo-writeoff-note').value = '';
            document.getElementById('depo-writeoff-modal').classList.add('active');
        }
```

- [ ] **Step 5: Add Adjust + Write-off to the row actions**

In `renderInventoryItems` (Task 1), extend the Actions cell so each row also offers Adjust and Write-off:

```javascript
                            <button class="btn btn-sm btn-warning" onclick="openAdjustModal(${it.id})" data-i18n="adjust_count">Adjust</button>
                            <button class="btn btn-sm btn-danger" onclick="openWriteoffModal(${it.id})" data-i18n="write_off">Write-off</button>
```

- [ ] **Step 6: Translation keys** (EN then AR, parallel):

```javascript
                // EN
                adjust_count: 'Adjust count', write_off: 'Write-off', quantity: 'Quantity',
                unit_cost: 'Unit cost', counted_qty: 'Counted quantity', expiry_date: 'Expiry date',
                note: 'Note', stock_added: 'Stock added.', count_adjusted: 'Count adjusted.',
                written_off: 'Written off.', now_low_stock: 'Item is now at/below its low-stock level.',
                unable_restock: 'Unable to add stock.', unable_adjust: 'Unable to adjust.', unable_writeoff: 'Unable to write off.',
```
```javascript
                // AR
                adjust_count: 'تعديل الجرد', write_off: 'شطب', quantity: 'الكمية',
                unit_cost: 'تكلفة الوحدة', counted_qty: 'الكمية المعدودة', expiry_date: 'تاريخ الصلاحية',
                note: 'ملاحظة', stock_added: 'تمت إضافة المخزون.', count_adjusted: 'تم تعديل الجرد.',
                written_off: 'تم الشطب.', now_low_stock: 'المادة الآن عند حد النقص أو أقل.',
                unable_restock: 'تعذّرت إضافة المخزون.', unable_adjust: 'تعذّر التعديل.', unable_writeoff: 'تعذّر الشطب.',
```

> If `note` / `quantity` already exist in the maps, reuse — don't duplicate (a duplicate key is a silent overwrite). The test only checks presence.

- [ ] **Step 7: Run tests + integrity** → `python -m pytest tests/test_depo_ui.py -q` PASS; import + `node --check` clean.

- [ ] **Step 8: Commit**

```bash
git add templates.py tests/test_depo_ui.py
git commit -m "feat(depo-ui): Add-stock / Adjust-count / Write-off actions"
```

---

### Task 4: Materials sub-panel on the Catalog procedure editor

**Files:**
- Modify: `templates.py` (materials panel inside the `treatments` tab; `loadProcedureMaterials`, `renderProcedureMaterials`, `addProcedureMaterial`, `removeProcedureMaterial`; populate item options from `inventoryItemsCache`; translation keys)
- Test: `tests/test_depo_ui.py`

**Interfaces:**
- Consumes: `inventoryItemsCache`/`loadInventoryItems` (Task 1), `treatmentProceduresCache` (existing).
- Produces: DOM ids `materials-procedure-select`, `materials-item-select`, `materials-default-qty`, `materials-body`; functions `loadProcedureMaterials()`, `renderProcedureMaterials(list)`, `addProcedureMaterial()`, `removeProcedureMaterial(itemId)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_depo_ui.py
def test_materials_subpanel_present():
    assert 'id="materials-procedure-select"' in HTML
    assert 'id="materials-item-select"' in HTML
    assert 'id="materials-body"' in HTML
    for fn in ('loadProcedureMaterials', 'renderProcedureMaterials',
               'addProcedureMaterial', 'removeProcedureMaterial'):
        assert f'function {fn}' in HTML, f'missing {fn}'
    assert '/materials' in HTML


def test_materials_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('procedure_materials', 'default_qty', 'link_material'):
        assert f'{key}:' in en and f'{key}:' in ar, f'missing {key}'
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Add the materials sub-panel**

Inside the `treatments` tab, after the procedures table `section-card` (search `id="catalog-subtab-procedure"`'s closing `</div><!-- /catalog-subtab-procedure -->` then the enclosing `section-card` close), add a new `section-card`:

```html
                    <div class="section-card">
                        <div class="section-card-header"><div>
                            <h3 data-i18n="procedure_materials">Procedure materials (Depo)</h3>
                            <p data-i18n="procedure_materials_summary">Link stock items consumed by a procedure and set the default amount issued.</p>
                        </div></div>
                        <div class="form-row-3">
                            <div class="form-group"><label data-i18n="procedure">Procedure</label>
                                <select id="materials-procedure-select" onchange="loadProcedureMaterials()"></select></div>
                            <div class="form-group"><label data-i18n="item">Item</label>
                                <select id="materials-item-select"></select></div>
                            <div class="form-group"><label data-i18n="default_qty">Default qty</label>
                                <input type="number" step="any" id="materials-default-qty" value="1"></div>
                        </div>
                        <div class="toolbar-row">
                            <button class="btn btn-primary" type="button" onclick="addProcedureMaterial()" data-i18n="link_material">+ Link material</button>
                        </div>
                        <div class="table-container" style="margin-top:12px;">
                            <table><thead><tr>
                                <th data-i18n="item">Item</th>
                                <th class="numeric-cell" data-i18n="default_qty">Default qty</th>
                                <th class="actions-cell" data-i18n="actions">Actions</th>
                            </tr></thead>
                            <tbody id="materials-body"><tr><td colspan="3" data-i18n="no_data">No data</td></tr></tbody></table>
                        </div>
                    </div>
```

- [ ] **Step 4: Add the JS**

```javascript
        function _fillMaterialsSelects() {
            const procSel = document.getElementById('materials-procedure-select');
            const itemSel = document.getElementById('materials-item-select');
            if (procSel) procSel.innerHTML = treatmentProceduresCache
                .map(p => `<option value="${p.id}">${escapeHtml(p.name || '')}</option>`).join('');
            if (itemSel) itemSel.innerHTML = inventoryItemsCache
                .map(it => `<option value="${it.id}">${escapeHtml(it.name || '')}</option>`).join('');
        }

        async function loadProcedureMaterials() {
            const procSel = document.getElementById('materials-procedure-select');
            const body = document.getElementById('materials-body');
            if (!procSel || !body) return;
            const pid = procSel.value;
            if (!pid) { renderProcedureMaterials([]); return; }
            const res = await fetch(`/api/inventory/procedures/${pid}/materials`);
            const links = await res.json().catch(() => []);
            renderProcedureMaterials(Array.isArray(links) ? links : []);
        }

        function renderProcedureMaterials(list) {
            const body = document.getElementById('materials-body');
            if (!body) return;
            body.innerHTML = list.length ? list.map(m => `<tr>
                <td>${escapeHtml(m.name || '')}</td>
                <td class="numeric-cell">${m.default_qty}</td>
                <td class="actions-cell"><button class="btn btn-sm btn-danger"
                    onclick="removeProcedureMaterial(${m.item_id})" data-i18n="remove">Remove</button></td>
            </tr>`).join('') : `<tr><td colspan="3">${t('no_data','No data')}</td></tr>`;
        }

        async function addProcedureMaterial() {
            const pid = document.getElementById('materials-procedure-select').value;
            const itemId = document.getElementById('materials-item-select').value;
            const qty = Number(document.getElementById('materials-default-qty').value);
            if (!pid || !itemId) { showToast(t('pick_procedure_item','Pick a procedure and an item.'), 'warning'); return; }
            const res = await fetch(`/api/inventory/procedures/${pid}/materials`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({item_id: Number(itemId), default_qty: qty})});
            if (!res.ok) { showToast(t('unable_link','Unable to link material.'), 'error'); return; }
            await loadProcedureMaterials();
        }

        async function removeProcedureMaterial(itemId) {
            const pid = document.getElementById('materials-procedure-select').value;
            const res = await fetch(`/api/inventory/procedures/${pid}/materials`, {
                method: 'DELETE', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({item_id: itemId})});
            if (!res.ok) { showToast(t('unable_unlink','Unable to remove link.'), 'error'); return; }
            await loadProcedureMaterials();
        }
```

- [ ] **Step 5: Populate the selects when the Catalog tab loads**

The Catalog tab loads via `loadTreatmentsSection()` (search it). At its end, ensure inventory items are loaded and the selects + materials list are populated:

```javascript
            await loadInventoryItems();
            _fillMaterialsSelects();
            loadProcedureMaterials();
```

> Add these lines inside `loadTreatmentsSection` after the procedures are loaded (so `treatmentProceduresCache` and `inventoryItemsCache` are both populated). If `loadTreatmentsSection` is not `async`, make it `async` (it already `await`s procedure loads in this codebase — confirm by reading it).

- [ ] **Step 6: Translation keys** (EN / AR parallel):

```javascript
                // EN
                procedure_materials: 'Procedure materials (Depo)',
                procedure_materials_summary: 'Link stock items consumed by a procedure and set the default amount issued.',
                default_qty: 'Default qty', link_material: '+ Link material', procedure: 'Procedure',
                remove: 'Remove', pick_procedure_item: 'Pick a procedure and an item.',
                unable_link: 'Unable to link material.', unable_unlink: 'Unable to remove link.',
```
```javascript
                // AR
                procedure_materials: 'مواد الإجراء (المخزن)',
                procedure_materials_summary: 'اربط مواد المخزون التي يستهلكها الإجراء وحدّد الكمية الافتراضية المصروفة.',
                default_qty: 'الكمية الافتراضية', link_material: '+ ربط مادة', procedure: 'الإجراء',
                remove: 'إزالة', pick_procedure_item: 'اختر إجراءً ومادة.',
                unable_link: 'تعذّر ربط المادة.', unable_unlink: 'تعذّرت إزالة الربط.',
```

- [ ] **Step 7: Run tests + integrity** → PASS; import + `node --check` clean.

- [ ] **Step 8: Commit**

```bash
git add templates.py tests/test_depo_ui.py
git commit -m "feat(depo-ui): procedure-materials sub-panel on the Catalog editor"
```

---

### Task 5: Follow-up "issued from stock" override rows

**Files:**
- Modify: `templates.py` (materials block in the follow-up form template literal; fetch links on procedure change; inject `materials` into the POST body; surface `stock_warnings`)
- Test: `tests/test_depo_ui.py`

**Interfaces:**
- Consumes: `updateFollowupProcedureUi` (existing), the follow-up form + its submit handler (existing), `/api/inventory/procedures/<id>/materials` (Task 4 backend).
- Produces: DOM id `followup-materials-wrap` (+ `followup-materials-body`); functions `loadFollowupMaterials(procedureId)`, `collectFollowupMaterials()`; the POST body gains `materials` when overrides exist; the response `stock_warnings` drive a toast.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_depo_ui.py
def test_followup_override_rows_present():
    assert 'id="followup-materials-wrap"' in HTML
    assert 'id="followup-materials-body"' in HTML
    assert 'function loadFollowupMaterials' in HTML
    assert 'function collectFollowupMaterials' in HTML
    assert 'stock_warnings' in HTML
    assert 'data.materials' in HTML  # overrides injected into POST body


def test_followup_override_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('issued_from_stock',):
        assert f'{key}:' in en and f'{key}:' in ar
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Add the materials block to the follow-up form**

In the follow-up form template literal (search `id="patient-followup-form"`), add — after the procedure/custom/tooth `form-row` and before the price `form-row-3` — a container the JS fills:

```html
                            <div class="form-group" id="followup-materials-wrap" style="display:none;">
                                <label>${t('issued_from_stock','Issued from stock')}</label>
                                <div id="followup-materials-body"></div>
                            </div>
```

- [ ] **Step 4: Load links on procedure change + render rows**

Add these functions (near `updateFollowupProcedureUi`):

```javascript
        async function loadFollowupMaterials(procedureId) {
            const wrap = document.getElementById('followup-materials-wrap');
            const body = document.getElementById('followup-materials-body');
            if (!wrap || !body) return;
            if (!procedureId) { wrap.style.display = 'none'; body.innerHTML = ''; return; }
            let links = [];
            try {
                const res = await fetch(`/api/inventory/procedures/${procedureId}/materials`);
                links = await res.json();
            } catch (_) { links = []; }
            if (!Array.isArray(links) || !links.length) { wrap.style.display = 'none'; body.innerHTML = ''; return; }
            wrap.style.display = 'block';
            body.innerHTML = links.map(m => `<div class="form-row" style="align-items:center;">
                <div class="form-group" style="flex:2;">${escapeHtml(m.name || '')}
                    <small style="color:var(--muted)">${m.base_unit || ''}</small></div>
                <div class="form-group" style="flex:1;">
                    <input type="number" step="any" class="followup-material-qty"
                           data-item-id="${m.item_id}" value="${m.default_qty}"></div>
            </div>`).join('');
        }

        function collectFollowupMaterials() {
            const out = [];
            document.querySelectorAll('#followup-materials-body .followup-material-qty').forEach(inp => {
                out.push({item_id: Number(inp.getAttribute('data-item-id')), qty: Number(inp.value)});
            });
            return out;
        }
```

- [ ] **Step 5: Trigger loadFollowupMaterials on procedure change**

`updateFollowupProcedureUi` already runs on the procedure select's `change` and once on render. At the end of `updateFollowupProcedureUi`, add:

```javascript
            loadFollowupMaterials(select.value || null);
```

- [ ] **Step 6: Inject overrides + surface warnings in the submit handler**

In the follow-up submit handler (search `JSON.stringify(data)` inside the `patient-followup-form` submit listener), just before the `fetch`, attach overrides:

```javascript
                const followupMaterials = collectFollowupMaterials();
                if (followupMaterials.length) data.materials = followupMaterials;
```

After a successful response, read warnings (replace the existing success branch's start so the parsed body is available):

```javascript
                const result = await response.json().catch(() => ({}));
                if (Array.isArray(result.stock_warnings) && result.stock_warnings.length) {
                    const names = result.stock_warnings.map(w => w.name).join(', ');
                    showToast(t('stock_low_after','Low stock after issuing: ') + names, 'warning');
                }
```

> Place the `result`/warnings read *after* the `if (!response.ok)` guard and *before* `viewPatientProfile(...)`. Do not change the billing preview or money fields — `materials` is additive to the existing payload.

- [ ] **Step 7: Translation keys** (EN / AR):

```javascript
                // EN
                issued_from_stock: 'Issued from stock',
                stock_low_after: 'Low stock after issuing: ',
```
```javascript
                // AR
                issued_from_stock: 'المصروف من المخزون',
                stock_low_after: 'مخزون منخفض بعد الصرف: ',
```

- [ ] **Step 8: Run tests + integrity** → PASS; import + `node --check` clean.

- [ ] **Step 9: Commit**

```bash
git add templates.py tests/test_depo_ui.py
git commit -m "feat(depo-ui): follow-up issued-from-stock override rows + low-stock toast"
```

---

### Task 6: Basic report panel (low-stock / on-hand value / expiring-soon)

**Files:**
- Modify: `templates.py` (report card in the Depo tab; `loadDepoReport`/`renderDepoReport`; call it from `loadDepoSection`; translation keys)
- Test: `tests/test_depo_ui.py`

**Interfaces:**
- Consumes: `GET /api/inventory/report`, `loadDepoSection` (Task 1).
- Produces: DOM ids `depo-report-low`, `depo-report-expiring`, `depo-report-value`; functions `loadDepoReport()`, `renderDepoReport(report)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_depo_ui.py
def test_report_panel_present():
    for did in ('depo-report-low', 'depo-report-expiring', 'depo-report-value'):
        assert f'id="{did}"' in HTML, f'missing {did}'
    assert 'function loadDepoReport' in HTML
    assert 'function renderDepoReport' in HTML
    assert "/api/inventory/report" in HTML


def test_report_strings_bilingual():
    en, ar = _lang_map('en'), _lang_map('ar')
    for key in ('low_stock_items', 'expiring_soon', 'on_hand_value'):
        assert f'{key}:' in en and f'{key}:' in ar
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Add the report card** to the `#depo` panel (after the items `section-card`):

```html
                    <div class="section-card">
                        <div class="section-card-header"><div>
                            <h3 data-i18n="depo_report">Stock report</h3>
                            <p data-i18n="on_hand_value">On-hand value</p>
                        </div><div><strong id="depo-report-value">0</strong></div></div>
                        <div class="form-row">
                            <div class="form-group" style="flex:1;">
                                <h4 data-i18n="low_stock_items">Low-stock items</h4>
                                <div id="depo-report-low"></div></div>
                            <div class="form-group" style="flex:1;">
                                <h4 data-i18n="expiring_soon">Expiring soon</h4>
                                <div id="depo-report-expiring"></div></div>
                        </div>
                    </div>
```

- [ ] **Step 4: Add the JS** and call from `loadDepoSection`:

```javascript
        async function loadDepoReport() {
            let report = {low_stock: [], expiring_soon: [], on_hand_value: 0};
            try { report = await (await fetch('/api/inventory/report')).json(); } catch (_) {}
            renderDepoReport(report || {});
        }

        function renderDepoReport(report) {
            const low = document.getElementById('depo-report-low');
            const exp = document.getElementById('depo-report-expiring');
            const val = document.getElementById('depo-report-value');
            const lowList = report.low_stock || [];
            const expList = report.expiring_soon || [];
            if (low) low.innerHTML = lowList.length
                ? lowList.map(i => `<div>${escapeHtml(i.name || '')} — <span class="badge badge-warning">${i.quantity}</span></div>`).join('')
                : `<div style="color:var(--muted)">${t('none','None')}</div>`;
            if (exp) exp.innerHTML = expList.length
                ? expList.map(i => `<div>${escapeHtml(i.name || '')} — ${i.expiry_date || ''}</div>`).join('')
                : `<div style="color:var(--muted)">${t('none','None')}</div>`;
            if (val) val.textContent = '₪ ' + (Number(report.on_hand_value) || 0).toFixed(2);
        }
```

Extend `loadDepoSection` (Task 1) to also load the report:

```javascript
        async function loadDepoSection() {
            await loadInventoryItems();
            renderInventoryItems();
            await loadDepoReport();
        }
```

- [ ] **Step 5: Translation keys** (EN / AR):

```javascript
                // EN
                depo_report: 'Stock report', low_stock_items: 'Low-stock items',
                expiring_soon: 'Expiring soon', on_hand_value: 'On-hand value', none: 'None',
```
```javascript
                // AR
                depo_report: 'تقرير المخزون', low_stock_items: 'مواد منخفضة المخزون',
                expiring_soon: 'قريبة الانتهاء', on_hand_value: 'قيمة المتوفر', none: 'لا يوجد',
```

- [ ] **Step 6: Run tests + integrity** → PASS; import + `node --check` clean.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_depo_ui.py
git commit -m "feat(depo-ui): basic stock report (low-stock, on-hand value, expiring-soon)"
```

---

### Task 7: Bilingual + behavioral smoke + regression gate

**Files:**
- Modify: `templates.py` (only if smoke surfaces a defect), `CHANGELOG.md` (add the Depo desktop-UI entry)
- Test: `tests/test_depo_ui.py` (balance check), full pytest suite, Playwright behavioral smoke

**Interfaces:** none new — this task verifies the whole feature end-to-end.

- [ ] **Step 1: Add a language-balance test**

```python
# append to tests/test_depo_ui.py
DEPO_KEYS = [
    'depo_title','depo_summary','add_item','items_in_stock','stock_value','item','on_hand',
    'packs_remaining','in_stock','low_stock','negative','add_stock','edit_item','item_name_required',
    'item_name_ar','base_unit','pack_unit','pack_size','low_stock_threshold','reorder_qty','supplier',
    'location','track_expiry','deactivate','unable_save_item','item_saved','item_deactivated',
    'adjust_count','write_off','quantity','unit_cost','counted_qty','expiry_date','note','stock_added',
    'count_adjusted','written_off','now_low_stock','unable_restock','unable_adjust','unable_writeoff',
    'procedure_materials','procedure_materials_summary','default_qty','link_material','procedure','remove',
    'pick_procedure_item','unable_link','unable_unlink','issued_from_stock','stock_low_after',
    'depo_report','low_stock_items','expiring_soon','on_hand_value','none',
]


def test_every_depo_key_in_both_languages():
    en, ar = _lang_map('en'), _lang_map('ar')
    missing_en = [k for k in DEPO_KEYS if f'{k}:' not in en]
    missing_ar = [k for k in DEPO_KEYS if f'{k}:' not in ar]
    assert not missing_en, f'EN missing: {missing_en}'
    assert not missing_ar, f'AR missing: {missing_ar}'
```

Run: `python -m pytest tests/test_depo_ui.py -q` → Expected: PASS. Fix any missing key the test reports.

- [ ] **Step 2: Full template + JS integrity**

```bash
python -c "import templates; print('import ok')"
```
Then the `node --check` sweep from Task 1 Step 8. Expected: `import ok` and `JS OK`.

- [ ] **Step 3: Full pytest suite (no regression)**

Run: `python -m pytest -q`
Expected: PASS — the prior ~730 tests plus the new `tests/test_depo_ui.py`. The UI is frontend-only; any red here means an edit corrupted the template (a `{` collision with Jinja, a dropped quote) — bisect with `import templates`.

- [ ] **Step 4: Playwright behavioral smoke (light + dark, EN + AR-RTL)**

Follow the project's web-smoke recipe (project memory `reference_web_visual_smoke`): launch the desktop server against a fresh temp DB **with a seeded active license** (otherwise the activation gate hides the app), log in `admin`/`admin`, then via Playwright (MCP):

1. Seed one item through the UI: open **Depo** tab → **+ Add Item** → name "Composite", base unit "compule", pack unit "box", pack size 20, threshold 5, **Track expiry** on → Save. Assert the row appears with an **In stock** badge.
2. **Add stock**: 30 @ 2.0 (+ an expiry date, since track-expiry is on) → assert on-hand shows 30, packs ≈ 1.5, stock value ≈ 60.
3. **Catalog → Procedure materials**: add a procedure "Filling", link Composite default qty 2 → assert it lists.
4. **Record a follow-up** for any patient with procedure "Filling" → assert the "Issued from stock" row pre-fills 2, save → assert Depo on-hand drops to 28.
5. Drop stock below threshold (Write-off 24) → assert the badge flips to **Low stock** and the report's Low-stock list includes Composite.
6. Toggle language to **AR** → assert the tab label reads **مخزن**, layout is RTL, and the table headers are Arabic. Toggle theme to **dark** → screenshot both. No console errors.

Record the screenshots/paths in the commit message or PR. If any step fails, fix in `templates.py` and re-run Steps 2–4.

- [ ] **Step 5: CHANGELOG entry**

Add a dated entry to `CHANGELOG.md` summarizing the desktop Depo UI (new tab, item management, stock actions, materials linking, follow-up issued-from-stock, report; EN/AR; consumes the engine API; insight-only).

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_depo_ui.py CHANGELOG.md
git commit -m "test(depo-ui): bilingual + behavioral smoke gate; CHANGELOG"
```

---

## Self-Review

**Spec coverage (spec §7 Desktop → task):**
- "New Depo section: item list with on-hand, packs-remaining, low-stock highlight, expiring-soon badge, total stock value" → Task 1 (+ expiring badge surfaced in the report, Task 6). ✅
- "Item editor (name EN/AR, category, units, pack, threshold, reorder_qty, supplier, location, Track-expiry checkbox, cost)" → Task 2. Note: `cost_per_unit` is set via **restock** (weighted-average), not typed in the editor — matches the engine (the editor exposing a raw cost would bypass weighted-average). The editor covers every other field. ✅
- "Actions: Add stock, Adjust count, Write-off, deactivate" → Task 3 (+ deactivate in Task 2). ✅
- "Materials sub-panel on the treatment-procedures editor" → Task 4. ✅
- "Follow-up form: editable consumption rows pre-filled with defaults; wording 'issued from stock'" → Task 5. ✅
- "Basic report panel: low-stock, on-hand value, expiring-soon" → Task 6. ✅
- "EN/AR" → every task adds both maps; Task 7 enforces balance. ✅
- "Behavioral Playwright smoke" → Task 7. ✅

**Placeholder scan:** every step contains the actual HTML/JS/test code; the only deferred specifics are *intentional reuse* notes ("if `escapeHtml` is absent, mirror the existing helper") that point at concrete existing functions to confirm by grep, not invented work. No "TBD"/"add validation"/"similar to Task N".

**Type/name consistency:** `loadDepoSection` → `loadInventoryItems` → `renderInventoryItems` consistent across Tasks 1/2/3/6; `inventoryItemsCache` shared; modal ids (`depo-item-modal`, `depo-restock-modal`, `depo-adjust-modal`, `depo-writeoff-modal`) unique and matched between HTML and handlers; `openModal`/`closeModal` reused (confirmed present in the template); the follow-up POST `materials` key matches the engine's expected `[{item_id, qty}]` (engine Task 6); `/api/inventory/procedures/<id>/materials` GET shape (`item_id`, `default_qty`, `name`, `base_unit`) matches what Tasks 4 & 5 render.

**Risk notes for the implementer:**
- **JS escaping trap is the #1 failure mode.** Run the `node --check` sweep after every task, not just at the end.
- **Duplicate translation keys silently overwrite.** Several keys here (`category`, `note`, `quantity`, `actions`, `active`, `cancel`, `save`, `edit`) may already exist — grep the maps first and reuse; only add what's missing. The tests assert *presence*, so a pre-existing key satisfies them.
- **Jinja vs JS braces:** the template is Jinja-rendered (`{{ }}`). Plain `{` / `}` in added `<script>`/CSS are fine, but never introduce a `{{` or `}}` pair in inline code.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-24-depo-inventory-desktop-ui.md`. Two execution options:
1. **Subagent-Driven (recommended)** — a fresh subagent per task, two-stage review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.
