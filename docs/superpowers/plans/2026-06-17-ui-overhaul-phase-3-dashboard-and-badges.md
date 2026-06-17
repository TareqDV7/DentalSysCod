# UI Overhaul Phase 3 — Editorial Dashboard + Color-Coded Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the desktop app's badges into one semantic, token-driven, dark-aware palette with a coherent status mapping, and restructure the dashboard into an editorial two-column layout (KPIs + quick actions rail | Today's Schedule + Recent Appointments) — using only existing endpoints.

**Architecture:** All work is in the single Flask template string `templates.py` (`HTML_TEMPLATE`) plus one new pytest file. Badges become one grouped-selector rule set (semantic name + legacy alias) with `body[data-theme="dark"]` variants; `getStatusBadgeClass()` is remapped. The dashboard `#dashboard` body is rebuilt as a two-column shell; a new `loadTodaySchedule()` filters `GET /api/appointments` client-side and reuses the Phase 2 skeleton loader.

**Tech Stack:** Python 3 / Flask, vanilla JS inside `HTML_TEMPLATE`, CSS custom properties (Phase 0 "Editorial Slate" tokens), pytest (substring-sentinel tests), Playwright (behavioral smoke).

**Spec:** `docs/superpowers/specs/2026-06-17-ui-overhaul-phase-3-dashboard-and-badges-design.md`

## Global Constraints

- **Branch:** all commits land on `feat/ui-overhaul-p3` (already checked out, rebased onto `origin/main` which includes Phase 0/1/2).
- **`HTML_TEMPLATE` is a NORMAL Python string** — JS template literals `${...}` are fine; **never introduce backslash escapes** (`\n`, `\d`) in inline JS (they collapse when Python parses the string and break the `<script>`). Verify with the render sweep in Task 7. See `reference_templates_js_escaping`.
- **Tests are substring sentinels:** `from templates import HTML_TEMPLATE` then `assert "…" in HTML_TEMPLATE` / `HTML_TEMPLATE.count("…") == N`. Mirror `tests/test_ui_phase2_skeletons.py`.
- **Run tests:** `python -m pytest tests/ -q` from repo root `C:/Users/MSI/Desktop/clinic`. The RTK summary line is suppressed; for a reliable count run `rtk proxy python -m pytest tests/ -q` or check `$LASTEXITCODE`. Single test: `python -m pytest tests/test_ui_phase3.py::test_name -q`.
- **No new backend endpoints, no DB/API changes. Desktop web only** (no Flutter). **Odontogram stays hidden** (`ODONTOGRAM_ENABLED = false`) — do not touch it.
- **Every new user-facing string gets a key in BOTH the `en` and `ar` translation dicts.** Commit attribution is disabled globally — no `Co-Authored-By` trailer.
- **Preserve element IDs** the JS already populates: `#total-patients`, `#today-appointments`, `#total-visits`, `#total-revenue`, `#stats-grid`, `#recent-appointments-table`, `#recent-appointments-body`, `#cloud-sync-badge`.

## File map

- **Modify:** `templates.py` (only production file touched)
  - CSS: badge consolidation replaces the `.badge-success…` block (~945) and **deletes** the duplicate `.badge-neutral…badge-blocked` block (~1708); dashboard two-column CSS added after the `.stats-grid` responsive rules (~1319).
  - Markup: `#dashboard` body rebuilt (~2213–2271).
  - i18n: new keys in the `en` dict and the `ar` dict.
  - JS: `getStatusBadgeClass()` remapped (~5174); `loadTodaySchedule()` added after `renderSkeletonRows` (~5212) / before `loadDashboard` (~5250); wired into `loadDashboard`.
- **Create:** `tests/test_ui_phase3.py`

---

### Task 1: Consolidated semantic badge palette + dark variants (CSS)

**Files:**
- Modify: `templates.py` (`.badge-success…` ~945–948; delete `.badge-neutral…` ~1708–1713)
- Test: `tests/test_ui_phase3.py`

**Interfaces:**
- Produces: CSS classes `.badge-success/.badge-warning/.badge-danger/.badge-info/.badge-neutral` (semantic) each grouped with their legacy alias (`.badge-active/.badge-pending/.badge-blocked/.badge-secondary/.badge-muted`), plus `body[data-theme="dark"]` variants. Consumed by Task 2 and all existing badge call sites.

- [ ] **Step 1: Write the failing test** — create `tests/test_ui_phase3.py`:

```python
from templates import HTML_TEMPLATE


def test_badges_consolidated_semantic_and_aliases():
    # semantic name + legacy alias share one rule (grouped selector)
    assert ".badge-success, .badge-active" in HTML_TEMPLATE
    assert ".badge-warning, .badge-pending" in HTML_TEMPLATE
    assert ".badge-danger, .badge-blocked" in HTML_TEMPLATE
    assert ".badge-info, .badge-secondary" in HTML_TEMPLATE
    assert ".badge-neutral, .badge-muted" in HTML_TEMPLATE


def test_badges_have_dark_variants():
    for cls in ("badge-success", "badge-warning", "badge-danger", "badge-info", "badge-neutral"):
        assert f'body[data-theme="dark"] .{cls}' in HTML_TEMPLATE


def test_old_duplicate_badge_block_removed():
    # the redundant hardcoded status-set definitions are gone
    assert ".badge-neutral { background: #eef4fb; color: #33536d; }" not in HTML_TEMPLATE
    assert ".badge-secondary { background: #e3f1ff; color: #1f5d9e; }" not in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase3.py -q`
Expected: FAIL (grouped selectors + dark variants absent; old block still present).

- [ ] **Step 3: Replace the semantic-badge block.** Replace these four lines (~945–948):

```css
        .badge-success { background: #e0f4e8; color: #166942; }
        .badge-warning { background: #fff1d4; color: #8b5e00; }
        .badge-danger { background: #ffe2e5; color: #8d1f33; }
        .badge-info { background: #e3f1ff; color: #1f5d9e; }
```

with the consolidated set (semantic + alias, light + dark):

```css
        /* ── Status badges — ONE semantic palette (P3). Each rule pairs the semantic
           name with its legacy alias so existing call sites keep working untouched. ── */
        .badge-success, .badge-active { background: #e0f4e8; color: #166942; }
        .badge-warning, .badge-pending { background: #fbeaca; color: #875600; }
        .badge-danger, .badge-blocked { background: #fbdfe2; color: #a11f2e; }
        .badge-info, .badge-secondary { background: var(--accent-soft); color: var(--accent-strong); }
        .badge-neutral, .badge-muted { background: #eef2f8; color: #4a5a6e; }
        /* dark variants — translucent fills + lightened ink (verify >= 4.5:1 on the slate card) */
        body[data-theme="dark"] .badge-success, body[data-theme="dark"] .badge-active { background: rgba(34,197,94,.16); color: #7ee2a8; }
        body[data-theme="dark"] .badge-warning, body[data-theme="dark"] .badge-pending { background: rgba(251,191,36,.18); color: #f3ca63; }
        body[data-theme="dark"] .badge-danger, body[data-theme="dark"] .badge-blocked { background: rgba(239,68,68,.20); color: #ff9aa6; }
        body[data-theme="dark"] .badge-info, body[data-theme="dark"] .badge-secondary { background: rgba(56,189,248,.16); color: #8fd3f7; }
        body[data-theme="dark"] .badge-neutral, body[data-theme="dark"] .badge-muted { background: rgba(148,163,184,.18); color: #c3cdda; }
```

- [ ] **Step 4: Delete the duplicate status-set block.** Remove these six lines (~1708–1713) entirely (now covered by the consolidated aliases above):

```css
        .badge-neutral { background: #eef4fb; color: #33536d; }
        .badge-active { background: #e0f4e8; color: #166942; }
        .badge-pending { background: #fff1d4; color: #8b5e00; }
        .badge-muted { background: #e9eef5; color: #596a7c; }
        .badge-secondary { background: #e3f1ff; color: #1f5d9e; }
        .badge-blocked { background: #ffe2e5; color: #8d1f33; }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase3.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_ui_phase3.py
git commit -m "feat(ui-p3): consolidate badges to one semantic palette + dark variants"
```

---

### Task 2: Remap `getStatusBadgeClass()` (coherent status mapping)

**Files:**
- Modify: `templates.py` (`getStatusBadgeClass` ~5174–5181)
- Test: `tests/test_ui_phase3.py`

**Interfaces:**
- Consumes: the semantic classes from Task 1.
- Produces: `getStatusBadgeClass(status)` returning a **semantic** class; consumed by `renderStatusBadge` (unchanged) at the recent/appointments tables and Task 6's Today's Schedule.

- [ ] **Step 1: Write the failing test** — append to `tests/test_ui_phase3.py`:

```python
def test_status_mapping_cancelled_is_danger_not_amber():
    # cancelled / no-show are terminal -> danger (red), no longer amber
    assert "normalized === 'cancelled' || normalized === 'no_show' || normalized === 'no-show') return 'badge-danger'" in HTML_TEMPLATE
    # the old muddled mapping is gone
    assert "normalized === 'cancelled' || normalized === 'postponed' || normalized === 'inactive') return 'badge-pending'" not in HTML_TEMPLATE


def test_status_mapping_uses_semantic_names():
    assert "normalized === 'scheduled' || normalized === 'confirmed') return 'badge-info'" in HTML_TEMPLATE
    assert "normalized === 'pending' || normalized === 'postponed') return 'badge-warning'" in HTML_TEMPLATE
    assert "normalized === 'completed' || normalized === 'paid' || normalized === 'active') return 'badge-success'" in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase3.py::test_status_mapping_cancelled_is_danger_not_amber tests/test_ui_phase3.py::test_status_mapping_uses_semantic_names -q`
Expected: FAIL.

- [ ] **Step 3: Replace the function body.** Replace `getStatusBadgeClass` (~5174):

```javascript
        function getStatusBadgeClass(status) {
            const normalized = String(status || '').toLowerCase();
            if (normalized === 'completed' || normalized === 'paid' || normalized === 'active') return 'badge-active';
            if (normalized === 'confirmed' || normalized === 'scheduled' || normalized === 'pending') return 'badge-secondary';
            if (normalized === 'cancelled' || normalized === 'postponed' || normalized === 'inactive') return 'badge-pending';
            if (normalized === 'error' || normalized === 'failed') return 'badge-blocked';
            return 'badge-neutral';
        }
```

with the coherent semantic mapping:

```javascript
        function getStatusBadgeClass(status) {
            const normalized = String(status || '').toLowerCase();
            if (normalized === 'completed' || normalized === 'paid' || normalized === 'active') return 'badge-success';
            if (normalized === 'scheduled' || normalized === 'confirmed') return 'badge-info';
            if (normalized === 'pending' || normalized === 'postponed') return 'badge-warning';
            if (normalized === 'cancelled' || normalized === 'no_show' || normalized === 'no-show') return 'badge-danger';
            if (normalized === 'error' || normalized === 'failed') return 'badge-danger';
            return 'badge-neutral';
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase3.py -q`
Expected: PASS.

- [ ] **Step 5: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_ui_phase3.py
git commit -m "feat(ui-p3): coherent status->badge mapping (cancelled=danger, not amber)"
```

---

### Task 3: i18n keys (EN + AR)

**Files:**
- Modify: `templates.py` (EN translations dict; AR translations dict)
- Test: `tests/test_ui_phase3.py`

**Interfaces:**
- Produces: i18n keys `today_schedule`, `quick_actions`, `new_appointment`, `no_appointments_today`, `loading_today`, `schedule_load_failed` — consumed by Tasks 5 & 6.

- [ ] **Step 1: Write the failing test** — append:

```python
def test_phase3_i18n_keys_present_both_langs():
    for key in ("today_schedule", "quick_actions", "new_appointment",
                "no_appointments_today", "loading_today", "schedule_load_failed"):
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase3.py::test_phase3_i18n_keys_present_both_langs -q`
Expected: FAIL.

- [ ] **Step 3: Add the keys.** In the **EN** dict (near the existing `dashboard_overview:` / `recent_appointments:` entries) add:

```javascript
                today_schedule: "Today's Schedule",
                quick_actions: 'Quick Actions',
                new_appointment: 'New Appointment',
                no_appointments_today: 'No appointments scheduled today.',
                loading_today: "Loading today's schedule...",
                schedule_load_failed: "Couldn't load today's schedule.",
```

In the **AR** dict (near the matching Arabic entries) add:

```javascript
                today_schedule: 'جدول اليوم',
                quick_actions: 'إجراءات سريعة',
                new_appointment: 'موعد جديد',
                no_appointments_today: 'لا توجد مواعيد مجدولة اليوم.',
                loading_today: 'جارٍ تحميل جدول اليوم...',
                schedule_load_failed: 'تعذّر تحميل جدول اليوم.',
```

(`add_new_patient`, `download_backup`, `patient`, `status`, `treatment_type`, `date_time` already exist and are reused — do not re-add.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase3.py::test_phase3_i18n_keys_present_both_langs -q`
Expected: PASS.

- [ ] **Step 5: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_ui_phase3.py
git commit -m "feat(ui-p3): EN/AR i18n keys for editorial dashboard"
```

---

### Task 4: Two-column dashboard shell CSS

**Files:**
- Modify: `templates.py` (CSS, after the `.stats-grid` 1-col rule ~1319)
- Test: `tests/test_ui_phase3.py`

**Interfaces:**
- Produces: `.dash-grid`, `.dash-rail`, `.dash-main`, `.stats-grid--rail`, `.quick-actions`, `.quick-actions__btn`, `.today-panel` — consumed by Task 5 markup.

- [ ] **Step 1: Write the failing test** — append:

```python
def test_dashboard_two_column_css_present():
    assert ".dash-grid" in HTML_TEMPLATE
    assert ".dash-rail" in HTML_TEMPLATE
    assert ".dash-main" in HTML_TEMPLATE
    assert ".quick-actions" in HTML_TEMPLATE
    # responsive: stacks at the narrow breakpoint
    assert ".dash-grid" in HTML_TEMPLATE[HTML_TEMPLATE.find("@media (max-width: 720px)"):]


def test_dashboard_rail_uses_logical_props_for_rtl():
    # the grid is defined with a logical column order so RTL mirrors for free
    assert "grid-template-columns" in HTML_TEMPLATE[HTML_TEMPLATE.find(".dash-grid"):HTML_TEMPLATE.find(".dash-grid") + 400]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase3.py::test_dashboard_two_column_css_present tests/test_ui_phase3.py::test_dashboard_rail_uses_logical_props_for_rtl -q`
Expected: FAIL.

- [ ] **Step 3: Add the CSS.** Insert immediately after the `.stats-grid { grid-template-columns: 1fr; }` 1-column rule (~1319):

```css
        /* ── P3 editorial dashboard: narrow rail + wide main (RTL-safe via grid order) ── */
        .dash-grid { display: grid; grid-template-columns: minmax(260px, 300px) 1fr; gap: 18px; align-items: start; }
        .dash-rail { display: flex; flex-direction: column; gap: 14px; }
        .dash-rail .stats-grid--rail { grid-template-columns: 1fr; gap: 12px; }
        .dash-main { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
        .quick-actions { display: flex; flex-direction: column; gap: 8px; background: var(--surface);
            border: 1px solid var(--surface-border); border-radius: var(--radius-lg); padding: 14px; }
        .quick-actions__title { font-size: .8rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: .04em; color: var(--muted); margin-bottom: 2px; }
        .quick-actions__btn { width: 100%; justify-content: flex-start; }
        .today-panel .today-empty { padding: 18px 14px; color: var(--muted); font-size: .92rem; }
        @media (max-width: 720px) {
            .dash-grid { grid-template-columns: 1fr; }
            .dash-rail .stats-grid--rail { grid-template-columns: 1fr 1fr; }
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase3.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_phase3.py
git commit -m "feat(ui-p3): two-column dashboard shell CSS (rail/main, responsive, RTL)"
```

---

### Task 5: Dashboard markup — editorial two-column

**Files:**
- Modify: `templates.py` (`#dashboard` body ~2213–2271)
- Test: `tests/test_ui_phase3.py`

**Interfaces:**
- Consumes: Task 4 CSS classes; i18n keys from Task 3.
- Produces: `#today-schedule-body` tbody (colSpan 4) + `.dash-grid` markup; preserves all existing IDs. Consumed by Task 6's `loadTodaySchedule`.

- [ ] **Step 1: Write the failing test** — append:

```python
def test_dashboard_markup_two_column_and_schedule():
    assert 'class="dash-grid"' in HTML_TEMPLATE
    assert 'class="dash-rail"' in HTML_TEMPLATE
    assert 'id="today-schedule-body"' in HTML_TEMPLATE
    # quick actions wired to real, existing handlers
    assert 'onclick="showAddPatientModal()"' in HTML_TEMPLATE
    assert 'onclick="showAddAppointmentModal()"' in HTML_TEMPLATE
    # KPI ids preserved so loadDashboard keeps populating them
    for el_id in ('total-patients', 'today-appointments', 'total-visits', 'total-revenue', 'recent-appointments-body'):
        assert f'id="{el_id}"' in HTML_TEMPLATE
    # KPI grid keeps its id + gains the rail modifier
    assert 'class="stats-grid stats-grid--rail" id="stats-grid"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase3.py::test_dashboard_markup_two_column_and_schedule -q`
Expected: FAIL.

- [ ] **Step 3: Replace the `#dashboard` body.** Replace the entire block from `<div id="dashboard" class="tab-content active">` through its matching close (~2213–2271) with:

```html
            <div id="dashboard" class="tab-content active">
                <div class="screen-shell">
                    <div class="section-card-header">
                        <div>
                            <h2 data-i18n="dashboard_overview">Dashboard Overview</h2>
                            <p data-i18n="dashboard_summary">Snapshot of today's activity, totals, and recent appointments.</p>
                        </div>
                        <div class="section-card-actions">
                            <span id="cloud-sync-badge" style="display:none;align-self:center;font-size:0.85em;color:var(--muted);"></span>
                            <button class="btn btn-primary" onclick="downloadBackup()" data-i18n="download_backup">💾 Download Backup</button>
                        </div>
                    </div>

                    <div class="dash-grid">
                        <aside class="dash-rail">
                            <div class="stats-grid stats-grid--rail" id="stats-grid">
                                <div class="stat-card stat-card-teal">
                                    <span class="stat-icon">👥</span>
                                    <h3 id="total-patients">0</h3>
                                    <p data-i18n="total_patients">Total Patients</p>
                                </div>
                                <div class="stat-card stat-card-blue">
                                    <span class="stat-icon">📅</span>
                                    <h3 id="today-appointments">0</h3>
                                    <p data-i18n="todays_appointments">Today's Appointments</p>
                                </div>
                                <div class="stat-card stat-card-green">
                                    <span class="stat-icon">🩺</span>
                                    <h3 id="total-visits">0</h3>
                                    <p data-i18n="todays_visits">Today's Visits</p>
                                </div>
                                <div class="stat-card stat-card-amber">
                                    <span class="stat-icon">💰</span>
                                    <h3 id="total-revenue">₪ 0</h3>
                                    <p data-i18n="todays_revenue">Today's Revenue</p>
                                </div>
                            </div>
                            <div class="quick-actions">
                                <div class="quick-actions__title" data-i18n="quick_actions">Quick Actions</div>
                                <button class="btn btn-primary quick-actions__btn" onclick="showAddPatientModal()" data-i18n="add_new_patient">+ Add New Patient</button>
                                <button class="btn btn-secondary quick-actions__btn" onclick="showAddAppointmentModal()" data-i18n="new_appointment">New Appointment</button>
                                <button class="btn btn-secondary quick-actions__btn" onclick="downloadBackup()" data-i18n="download_backup">💾 Download Backup</button>
                            </div>
                        </aside>

                        <div class="dash-main">
                            <div class="section-card table-shell today-panel">
                                <div class="table-meta">
                                    <div>
                                        <div class="section-card-title" data-i18n="today_schedule">Today's Schedule</div>
                                        <div class="table-meta-text" data-i18n="todays_appointments">Today's Appointments</div>
                                    </div>
                                </div>
                                <div class="responsive-table-wrap">
                                    <table id="today-schedule-table">
                                        <thead>
                                            <tr>
                                                <th data-i18n="date_time">Date &amp; Time</th>
                                                <th data-i18n="patient">Patient</th>
                                                <th data-i18n="treatment_type">Treatment Type</th>
                                                <th class="center-cell" data-i18n="status">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody id="today-schedule-body"></tbody>
                                    </table>
                                </div>
                            </div>

                            <div class="section-card table-shell">
                                <div class="table-meta">
                                    <div>
                                        <div class="section-card-title" data-i18n="recent_appointments">Recent Appointments</div>
                                        <div class="table-meta-text" data-i18n="recent_appointments_hint">Latest scheduled visits and their current status.</div>
                                    </div>
                                </div>
                                <div class="responsive-table-wrap">
                                    <table id="recent-appointments-table">
                                        <thead>
                                            <tr>
                                                <th data-i18n="patient">Patient</th>
                                                <th data-i18n="date_time">Date &amp; Time</th>
                                                <th data-i18n="treatment_type">Treatment Type</th>
                                                <th class="center-cell" data-i18n="status">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody id="recent-appointments-body"></tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase3.py::test_dashboard_markup_two_column_and_schedule -q`
Expected: PASS.

- [ ] **Step 5: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_ui_phase3.py
git commit -m "feat(ui-p3): editorial two-column dashboard markup (+ Today's Schedule panel)"
```

---

### Task 6: `loadTodaySchedule()` + wire into `loadDashboard()`

**Files:**
- Modify: `templates.py` (add `loadTodaySchedule` after `renderSkeletonRows` ~5212; call it inside `loadDashboard` ~5250)
- Test: `tests/test_ui_phase3.py`

**Interfaces:**
- Consumes: existing helpers `getAppointmentDateValue`, `parseAppointmentDate`, `formatApptDate`, `renderStatusBadge`, `renderSkeletonRows`, `renderStateRow`, `safeDisplayText`, `t`; element `#today-schedule-body` (Task 5); i18n keys (Task 3); endpoint `GET /api/appointments`.
- Produces: `function loadTodaySchedule()` called by `loadDashboard`.

- [ ] **Step 1: Write the failing test** — append:

```python
def test_load_today_schedule_present_and_wired():
    assert "function loadTodaySchedule(" in HTML_TEMPLATE
    # reuses the P2 skeleton loader and the existing endpoint, no new API
    assert "renderSkeletonRows(4" in HTML_TEMPLATE
    assert "fetch('/api/appointments')" in HTML_TEMPLATE
    # called from loadDashboard
    idx = HTML_TEMPLATE.find("async function loadDashboard()")
    assert idx != -1
    assert "loadTodaySchedule()" in HTML_TEMPLATE[idx:idx + 900]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase3.py::test_load_today_schedule_present_and_wired -q`
Expected: FAIL.

- [ ] **Step 3: Add the helper.** Insert immediately after the `renderSkeletonRows` function's closing brace (~5215, before the `// Dashboard` comment):

```javascript
        // Today's Schedule — today's appointments, time-ascending, derived client-side
        // from the existing /api/appointments list (no new endpoint). Reuses the P2
        // skeleton loader; empty/error states reuse renderStateRow.
        function isSameLocalDay(date, ref) {
            return date.getFullYear() === ref.getFullYear()
                && date.getMonth() === ref.getMonth()
                && date.getDate() === ref.getDate();
        }

        async function loadTodaySchedule() {
            const body = document.getElementById('today-schedule-body');
            if (!body) return;
            body.innerHTML = renderSkeletonRows(4, { rows: 4, announce: t('loading_today', "Loading today's schedule...") });
            try {
                const appointments = await fetch('/api/appointments').then(r => r.json());
                const now = new Date();
                const todays = (Array.isArray(appointments) ? appointments : [])
                    .map(apt => ({ apt, d: parseAppointmentDate(getAppointmentDateValue(apt)) }))
                    .filter(x => x.d && isSameLocalDay(x.d, now))
                    .sort((a, b) => a.d.getTime() - b.d.getTime());
                if (!todays.length) {
                    body.innerHTML = renderStateRow(t('no_appointments_today', 'No appointments scheduled today.'), {
                        icon: '📭', title: t('no_appointments_today', 'No appointments scheduled today.'), colSpan: 4, kind: 'empty'
                    });
                    return;
                }
                body.innerHTML = todays.map(({ apt }) => `
                    <tr>
                        <td>${formatApptDate(getAppointmentDateValue(apt)) || t('no_data', 'No data')}</td>
                        <td>${safeDisplayText(apt.patient_name, t('no_data', 'No data'))}</td>
                        <td>${safeDisplayText(apt.treatment_type, t('no_data', 'No data'))}</td>
                        <td class="center-cell">${renderStatusBadge(apt.status, safeDisplayText(apt.status, 'scheduled'))}</td>
                    </tr>
                `).join('');
            } catch (error) {
                body.innerHTML = renderStateRow(t('schedule_load_failed', "Couldn't load today's schedule."), {
                    icon: '⚠️', title: t('schedule_load_failed', "Couldn't load today's schedule."), colSpan: 4, kind: 'error',
                    buttonHtml: `<button class="btn btn-primary" type="button" onclick="loadTodaySchedule()">${t('refresh', 'Refresh')}</button>`
                });
            }
        }
```

- [ ] **Step 4: Wire it into `loadDashboard`.** In `loadDashboard()` (~5250), immediately after the `refreshCloudBadge();` line, add the fire-and-forget call (runs in parallel with the stats + recent fetches — no waterfall):

```javascript
            refreshCloudBadge();
            loadTodaySchedule();
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase3.py::test_load_today_schedule_present_and_wired -q`
Expected: PASS.

- [ ] **Step 6: Render sweep**

Run: `python -c "import templates; assert 'function loadTodaySchedule(' in templates.HTML_TEMPLATE; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_ui_phase3.py
git commit -m "feat(ui-p3): Today's Schedule panel (client-side filter of /api/appointments)"
```

---

### Task 7: Full verification (suite + render sweep + Playwright smoke)

**Files:** none (verification only)

- [ ] **Step 1: Full pytest suite**

Run: `rtk proxy python -m pytest tests/ -q`
Expected: exit 0. No existing test regressed; all `tests/test_ui_phase3.py` tests pass.

- [ ] **Step 2: Final escaping/render sweep**

Run: `python -c "import templates; h=templates.HTML_TEMPLATE; assert h.count('alert(')==0 and h.count('confirm(')==0 and h.count('prompt(')==2; assert 'function loadTodaySchedule(' in h and '.dash-grid' in h; print('p3 clean')"`
Expected: prints `p3 clean` (P2 dialog invariant still holds; P3 symbols present).

- [ ] **Step 3: Playwright behavioral smoke** (gated on a seeded active license — see `reference_web_visual_smoke`: fresh temp DB, login admin/admin, force theme via `data-theme`). Drive the running portal and assert:
  - Dashboard renders as two columns (rail + main); the KPI rail shows 4 cards; Quick Actions buttons present and open their modals.
  - Today's Schedule populates from `/api/appointments` (or shows the empty state with no appointments today); rows show correct status badge colors.
  - Badge colors are correct in **both** light and dark: a cancelled appointment is **red** (not amber); scheduled is blue; completed is green.
  - Force `dir="rtl"` (Arabic) → the rail/main columns mirror; below 720px the columns stack.
  - **Zero JS console errors** across the run.

- [ ] **Step 4: Commit (only if Playwright produced fixtures/artifacts; otherwise skip)**

```bash
git add -A
git commit -m "test(ui-p3): Playwright behavioral smoke for dashboard + badges"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Badge consolidation → one semantic palette on tokens, dark variants, aliases kept → Task 1 ✓
- Coherent `renderStatusBadge`/`getStatusBadgeClass` mapping (cancelled≠pending) → Task 2 ✓
- Editorial two-column dashboard (rail: KPIs + quick actions; main: Today's Schedule + Recent) → Tasks 4 (CSS), 5 (markup) ✓
- Today's Schedule from existing `/api/appointments`, client-side filter, P2 skeleton reuse → Task 6 ✓
- i18n EN+AR for new strings → Task 3 ✓
- Dark theme + RTL + responsive stack → Tasks 1 (dark badges), 4 (responsive/RTL CSS), 7 (smoke) ✓
- No new endpoints / odontogram untouched / dialog invariant held → constraints + Task 7 sweep ✓
- Tests (pytest sentinels + render sweep + Playwright) → every task + Task 7 ✓

**Placeholder scan:** No TBD/TODO; every code step shows the exact code. Dark RGBA values are concrete (verify-contrast is a smoke check, not a placeholder).

**Type/name consistency:** `getStatusBadgeClass`/`renderStatusBadge`/`renderSkeletonRows`/`renderStateRow`/`loadTodaySchedule`/`isSameLocalDay`, classes `.dash-grid`/`.dash-rail`/`.dash-main`/`.stats-grid--rail`/`.quick-actions`/`.today-panel`, ids `#today-schedule-body`/`#stats-grid`/`#recent-appointments-body`, semantic badge classes + aliases — all used consistently across CSS, markup, JS, and tests. Quick-action handlers (`showAddPatientModal`, `showAddAppointmentModal`, `downloadBackup`) verified to exist in `templates.py`.
