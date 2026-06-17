# UI Overhaul Phase 2 — Destructive-Action Modal + Skeleton Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every reachable native browser dialog in the desktop app with designed UI — a promise-based confirm modal for the 7 destructive dialogs and `showToast()` for the 33 informational alerts — and add shimmer skeleton screens to the shared table loader and the patient-profile load.

**Architecture:** All work is in the single Flask template string `templates.py` (`HTML_TEMPLATE`) plus one new pytest file. The confirm modal reuses the app's existing `.modal`/`.modal-content`/`.modal-header` classes (instant light/dark theme parity) and adds a single injected `#confirm-modal` node driven by a Promise-based controller (`showConfirm`/`showTypedConfirm`). Skeletons reuse the existing shared-loader call sites via a new `renderSkeletonRows()` helper and a `renderProfileSkeleton()` block.

**Tech Stack:** Python 3 / Flask, vanilla JS inside `HTML_TEMPLATE`, CSS custom properties (Phase 0 "Editorial Slate" tokens), pytest (substring-sentinel tests), Playwright (behavioral smoke).

**Spec:** `docs/superpowers/specs/2026-06-16-ui-overhaul-phase-2-modal-and-skeletons-design.md`

---

## Critical conventions (read before starting)

1. **`HTML_TEMPLATE` is a NORMAL Python string** (not f-string, not `.format()`, not Jinja-rendered for the inline JS). JS template literals `${...}` are safe and used throughout. **The JS-escaping trap:** a bare `'\n'` or regex `\d` inside the inline JS collapses when Python parses the string and breaks the entire `<script>`. This phase's code intentionally avoids backslash escapes; do not introduce any. Verify with the render sweep in Task 11.
2. **Tests are substring sentinels.** The harness is `from templates import HTML_TEMPLATE` then `assert "..." in HTML_TEMPLATE` / `HTML_TEMPLATE.count("...") >= N`. Mirror `tests/test_billing_preview_p1.py` exactly.
3. **Run tests with** `python -m pytest tests/ -q` from the repo root (`C:/Users/MSI/Desktop/clinic`). The summary line is suppressed in this environment — check `$LASTEXITCODE` (PowerShell) / `echo $?` (bash). A single test: `python -m pytest tests/test_ui_phase2.py::test_name -q`.
4. **Branch:** all commits land on `feat/ui-overhaul-p2` (already checked out, based on merged `main`).
5. **Icons** use literal unicode chars (`⚠`, `ℹ`) consistent with existing emoji usage in the template — no sprite dependency.
6. **Commit message attribution is disabled globally** (per the user's `~/.claude/settings.json`); do not add a `Co-Authored-By` trailer.

---

## File map

- **Modify:** `templates.py` (only production file touched)
  - CSS: confirm-modal rules after `.modal-header` block (~line 1108); skeleton rules after `.loading-state` block (~line 1596).
  - Markup: `#confirm-modal` node after the last existing modal (`#tooth-popup`, ~line 3110).
  - i18n: 3 new keys in the `en` dict and the `ar` dict (translations object, ~lines 3322 EN / ~3732 AR).
  - JS: controller after the global Escape handler (`closeModal` block, ~line 4819); `renderSkeletonRows`/`renderProfileSkeleton` after `renderStateRow` (~line 4991); migrations at the enumerated call sites.
- **Create:** `tests/test_ui_phase2.py`

---

### Task 1: i18n keys (EN + AR)

**Files:**
- Modify: `templates.py` (EN dict ~3322, AR dict ~3732)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_ui_phase2.py` with:

```python
from templates import HTML_TEMPLATE


def test_phase2_i18n_keys_present_both_langs():
    for key in ("please_confirm", "confirm", "type_to_confirm"):
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_phase2_i18n_keys_present_both_langs -q`
Expected: FAIL (`please_confirm`/`type_to_confirm` not found ≥2 times).

- [ ] **Step 3: Add the keys.** In the **EN** translations dict (near the existing `loading:` / `cancel:` entries, ~line 3322), add:

```javascript
                please_confirm: 'Please confirm',
                confirm: 'Confirm',
                type_to_confirm: 'Type {word} to confirm.',
```

In the **AR** translations dict (near the matching entries, ~line 3732), add:

```javascript
                please_confirm: 'يرجى التأكيد',
                confirm: 'تأكيد',
                type_to_confirm: 'اكتب {word} للتأكيد.',
```

(Note: `cancel` and `delete` keys already exist and are reused via `t()` fallbacks — do not re-add.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_phase2_i18n_keys_present_both_langs -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): EN/AR i18n keys for confirm modal"
```

---

### Task 2: Confirm-modal CSS

**Files:**
- Modify: `templates.py` (CSS, after the `.modal-header h2` rules ~line 1108)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_ui_phase2.py`:

```python
def test_confirm_modal_css_present():
    assert ".modal--confirm" in HTML_TEMPLATE
    assert ".confirm-modal__icon" in HTML_TEMPLATE
    assert ".confirm-modal--danger" in HTML_TEMPLATE
    assert ".confirm-modal__ok:disabled" in HTML_TEMPLATE
    # danger button uses the Phase 0 danger token, solid (never frosted)
    assert "var(--danger)" in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_confirm_modal_css_present -q`
Expected: FAIL.

- [ ] **Step 3: Add the CSS** immediately after the `.modal-header h2 { ... }` rule (~line 1108):

```css
        /* ── Confirm / typed-confirm modal (reuses .modal/.modal-content) ── */
        .modal--confirm .modal-content { max-width: 400px; text-align: start; }
        .confirm-modal__icon {
            width: 44px; height: 44px; border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px; margin-bottom: 12px;
        }
        .confirm-modal--danger .confirm-modal__icon { background: rgba(217,67,78,.12); color: var(--danger); }
        .confirm-modal--neutral .confirm-modal__icon { background: var(--accent-soft); color: var(--accent-strong); }
        .confirm-modal__msg { font-size: 0.95rem; line-height: 1.55; color: var(--text-muted, #5b6675); margin: 0 0 16px; }
        .confirm-modal__typed { margin: 0 0 14px; }
        .confirm-modal__input {
            width: 100%; box-sizing: border-box; border: 1.5px solid var(--surface-border);
            border-radius: 10px; padding: 9px 11px; font-size: 0.95rem;
            background: var(--card, #fff); color: var(--text);
        }
        .confirm-modal__hint { font-size: 0.8rem; color: var(--text-muted, #5b6675); margin-top: 6px; }
        .confirm-modal__actions { display: flex; gap: 10px; justify-content: flex-end; }
        .confirm-modal__cancel { background: transparent; border: 1px solid var(--surface-border); color: var(--text); }
        .confirm-modal--danger .confirm-modal__ok { background: var(--danger); color: #fff; border: none; }
        .confirm-modal--neutral .confirm-modal__ok { background: var(--accent-gradient); color: #fff; border: none; }
        .confirm-modal__ok:disabled { background: #e6e9ee; color: #aeb4bd; cursor: not-allowed; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_confirm_modal_css_present -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): confirm-modal CSS (danger/neutral/typed, P0 tokens)"
```

---

### Task 3: Confirm-modal markup

**Files:**
- Modify: `templates.py` (after the `#tooth-popup` modal block, ~line 3110)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_confirm_modal_markup_present():
    assert 'id="confirm-modal"' in HTML_TEMPLATE
    assert 'role="dialog"' in HTML_TEMPLATE
    assert 'aria-modal="true"' in HTML_TEMPLATE
    assert 'id="confirm-modal-title"' in HTML_TEMPLATE
    assert 'class="confirm-modal__input"' in HTML_TEMPLATE
    assert 'class="btn confirm-modal__ok"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_confirm_modal_markup_present -q`
Expected: FAIL.

- [ ] **Step 3: Add the markup** immediately after the closing `</div>` of the `#tooth-popup` modal (~line 3110):

```html
    <div id="confirm-modal" class="modal modal--confirm confirm-modal--danger" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
        <div class="modal-content">
            <div class="confirm-modal__icon" aria-hidden="true">⚠</div>
            <div class="modal-header"><h2 id="confirm-modal-title"></h2></div>
            <p class="confirm-modal__msg"></p>
            <div class="confirm-modal__typed" hidden>
                <input class="confirm-modal__input" type="text" autocomplete="off" spellcheck="false">
                <div class="confirm-modal__hint"></div>
            </div>
            <div class="confirm-modal__actions">
                <button type="button" class="btn confirm-modal__cancel"></button>
                <button type="button" class="btn confirm-modal__ok"></button>
            </div>
        </div>
    </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_confirm_modal_markup_present -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): inject #confirm-modal markup (a11y dialog)"
```

---

### Task 4: Confirm-modal controller JS

**Files:**
- Modify: `templates.py` (JS, after the global Escape handler ~line 4819)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_confirm_controller_present():
    for fn in ("function showConfirm", "function showTypedConfirm",
               "function _openConfirm", "function _closeConfirm"):
        assert fn in HTML_TEMPLATE, f"{fn} missing"
    # capture-phase keydown so it resolves before the global Escape handler
    assert "addEventListener('keydown', _confirmKeydownHandler, true)" in HTML_TEMPLATE
    # backdrop/Esc/cancel resolve false; only ok/Enter resolve true
    assert "_closeConfirm(false)" in HTML_TEMPLATE
    assert "_closeConfirm(true)" in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_confirm_controller_present -q`
Expected: FAIL.

- [ ] **Step 3: Add the controller** immediately after the global Escape `document.addEventListener('keydown', ...)` block (~line 4819):

```javascript
        // ── Confirm / typed-confirm modal controller ─────────────────────────
        // Promise-based replacements for the native blocking dialogs. Reuse the
        // existing .modal/.modal-content classes (theme parity). Single instance,
        // injected once as #confirm-modal. Esc / backdrop / Cancel resolve(false);
        // Enter (outside the input) / OK resolve(true). The keydown listener is
        // registered in CAPTURE phase so it resolves the promise and stops the
        // event before the global Escape handler merely hides the node.
        let _confirmResolver = null;
        let _confirmLastFocus = null;
        let _confirmKeydownHandler = null;

        function _confirmModalEl() { return document.getElementById('confirm-modal'); }

        function _closeConfirm(result) {
            const m = _confirmModalEl();
            if (m) m.classList.remove('active');
            if (_confirmKeydownHandler) {
                document.removeEventListener('keydown', _confirmKeydownHandler, true);
                _confirmKeydownHandler = null;
            }
            const resolve = _confirmResolver;
            _confirmResolver = null;
            const last = _confirmLastFocus;
            _confirmLastFocus = null;
            if (last && typeof last.focus === 'function') last.focus();
            if (resolve) resolve(result);
        }

        function showConfirm(opts) {
            const o = opts || {};
            const danger = o.danger !== false;
            const m = _confirmModalEl();
            if (!m) return Promise.resolve(false);
            if (_confirmResolver) _closeConfirm(false);
            m.classList.toggle('confirm-modal--danger', danger);
            m.classList.toggle('confirm-modal--neutral', !danger);
            m.querySelector('#confirm-modal-title').textContent = o.title || t('please_confirm', 'Please confirm');
            m.querySelector('.confirm-modal__msg').textContent = o.message || '';
            m.querySelector('.confirm-modal__icon').textContent = danger ? '⚠' : 'ℹ';
            m.querySelector('.confirm-modal__typed').hidden = true;
            const okBtn = m.querySelector('.confirm-modal__ok');
            okBtn.disabled = false;
            okBtn.textContent = o.confirmLabel || (danger ? t('delete', 'Delete') : t('confirm', 'Confirm'));
            m.querySelector('.confirm-modal__cancel').textContent = o.cancelLabel || t('cancel', 'Cancel');
            return _openConfirm(m.querySelector('.confirm-modal__cancel'));
        }

        function showTypedConfirm(opts) {
            const o = opts || {};
            const word = String(o.word || '');
            const m = _confirmModalEl();
            if (!m) return Promise.resolve(false);
            if (_confirmResolver) _closeConfirm(false);
            m.classList.add('confirm-modal--danger');
            m.classList.remove('confirm-modal--neutral');
            m.querySelector('#confirm-modal-title').textContent = o.title || t('please_confirm', 'Please confirm');
            m.querySelector('.confirm-modal__msg').textContent = o.message || '';
            m.querySelector('.confirm-modal__icon').textContent = '⚠';
            m.querySelector('.confirm-modal__typed').hidden = false;
            const input = m.querySelector('.confirm-modal__input');
            input.value = '';
            m.querySelector('.confirm-modal__hint').textContent =
                t('type_to_confirm', 'Type {word} to confirm.').replace('{word}', word);
            const okBtn = m.querySelector('.confirm-modal__ok');
            okBtn.textContent = o.confirmLabel || t('confirm', 'Confirm');
            okBtn.disabled = true;
            input.oninput = function () { okBtn.disabled = input.value.trim() !== word; };
            m.querySelector('.confirm-modal__cancel').textContent = t('cancel', 'Cancel');
            return _openConfirm(input);
        }

        function _openConfirm(focusEl) {
            const m = _confirmModalEl();
            return new Promise(function (resolve) {
                _confirmResolver = resolve;
                _confirmLastFocus = document.activeElement;
                const okBtn = m.querySelector('.confirm-modal__ok');
                const cancelBtn = m.querySelector('.confirm-modal__cancel');
                okBtn.onclick = function () { _closeConfirm(true); };
                cancelBtn.onclick = function () { _closeConfirm(false); };
                m.onclick = function (e) { if (e.target === m) _closeConfirm(false); };
                _confirmKeydownHandler = function (e) {
                    if (e.key === 'Escape') {
                        e.preventDefault(); e.stopPropagation(); _closeConfirm(false);
                    } else if (e.key === 'Enter') {
                        if (document.activeElement === cancelBtn) return;
                        if (!okBtn.disabled) { e.preventDefault(); _closeConfirm(true); }
                    } else if (e.key === 'Tab') {
                        const f = Array.prototype.slice.call(m.querySelectorAll('button, input'))
                            .filter(function (el) { return !el.disabled && el.offsetParent !== null; });
                        if (!f.length) return;
                        const first = f[0], lastEl = f[f.length - 1];
                        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastEl.focus(); }
                        else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); first.focus(); }
                    }
                };
                document.addEventListener('keydown', _confirmKeydownHandler, true);
                m.classList.add('active');
                requestAnimationFrame(function () { (focusEl || okBtn).focus(); });
            });
        }
```

- [ ] **Step 4: Remove the now-obsolete comment.** Find the toast-section comment (~line 3975) that reads `blocking confirm()/prompt() stay until the` (and the surrounding two comment lines mentioning native `alert()`). Replace those lines with:

```javascript
        // Transient, non-blocking messages. Use showToast() for info/errors and
        // showConfirm()/showTypedConfirm() for blocking decisions — no native dialogs.
        // type is one of success|error|warning|info.
```

(This keeps the file free of literal `alert(` / `confirm(` / `prompt(` text in comments, so the Task 7 regression counts are clean.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_confirm_controller_present -q`
Expected: PASS.

- [ ] **Step 6: Render sweep (escaping guard).** Confirm the template still imports and renders (a broken inline `<script>` would not be caught by substring tests):

Run: `python -c "import templates; assert 'function showConfirm' in templates.HTML_TEMPLATE; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): promise-based showConfirm/showTypedConfirm controller"
```

---

### Task 5: Migrate the 6 `confirm()` call sites

Each native `confirm()` becomes `await showConfirm({...})`. The enclosing function **must be `async`**; all six already `await fetch(...)` downstream, but verify each declaration has `async` and add it if missing (search upward for the nearest `function name(` / `name = function(` / arrow and prefix with `async`).

**Files:**
- Modify: `templates.py` (6 call sites — anchor on the unique `confirm(` line, not the line number)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_no_native_confirm_remains():
    # all 6 confirm() sites migrated; controller uses no native fallback
    assert HTML_TEMPLATE.count("confirm(") == 0, "a native confirm( call still remains"

def test_confirm_sites_use_showconfirm():
    assert HTML_TEMPLATE.count("await showConfirm(") >= 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_no_native_confirm_remains tests/test_ui_phase2.py::test_confirm_sites_use_showconfirm -q`
Expected: FAIL (6 native `confirm(` present).

- [ ] **Step 3: Replace each site.** Apply these exact transformations (old → new). For each, also ensure the enclosing function is `async`.

Delete-holiday (~5369):
```javascript
// OLD
            if (!confirm(t('delete_holiday_confirm', 'Delete this holiday?'))) return;
// NEW
            if (!(await showConfirm({ message: t('delete_holiday_confirm', 'Delete this holiday?'), confirmLabel: t('delete', 'Delete') }))) return;
```

Generic delete (~5708):
```javascript
// OLD
            if (!confirm(t('confirm_delete', 'Are you sure you want to delete?'))) return;
// NEW
            if (!(await showConfirm({ message: t('confirm_delete', 'Are you sure you want to delete?'), confirmLabel: t('delete', 'Delete') }))) return;
```

Delete-expense (~6033):
```javascript
// OLD
            if (!confirm(t('delete_expense_confirm', 'Delete this expense?'))) return;
// NEW
            if (!(await showConfirm({ message: t('delete_expense_confirm', 'Delete this expense?'), confirmLabel: t('delete', 'Delete') }))) return;
```

Clear-catalogs (~6106, `clearCatalogs` — already `async`):
```javascript
// OLD
          if (!confirm(msg)) return;
// NEW
          if (!(await showConfirm({ message: msg, confirmLabel: t('delete', 'Delete') }))) return;
```

Generic delete (~7045):
```javascript
// OLD
            if (!confirm(t('confirm_delete', 'Are you sure you want to delete?'))) return;
// NEW
            if (!(await showConfirm({ message: t('confirm_delete', 'Are you sure you want to delete?'), confirmLabel: t('delete', 'Delete') }))) return;
```
(There are two identical `confirm_delete` lines — at ~5708 and ~7045. Replace **both**; the `old → new` string is identical, so apply the edit to each occurrence.)

Delete-patient (~7472, `deletePatient` — already `async`):
```javascript
// OLD
            if (!confirm(t('confirm_delete_patient', 'Are you sure you want to delete this patient?'))) return;
// NEW
            if (!(await showConfirm({ message: t('confirm_delete_patient', 'Are you sure you want to delete this patient?'), confirmLabel: t('delete', 'Delete') }))) return;
```

For the two non-fetch-obvious handlers (delete-holiday ~5369, delete-expense ~6033): confirm the function that contains each line is declared `async`. If the declaration lacks `async` (e.g. `function deleteHoliday(` → `async function deleteHoliday(`), add it. Check callers don't use the return value synchronously (these are `onclick` handlers; return value is ignored — safe).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_no_native_confirm_remains tests/test_ui_phase2.py::test_confirm_sites_use_showconfirm -q`
Expected: PASS.

- [ ] **Step 5: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): migrate 6 confirm() sites to showConfirm"
```

---

### Task 6: Migrate the DB-import `prompt()` to `showTypedConfirm`

**Files:**
- Modify: `templates.py` (`startDataImport`, ~line 6080 — already `async`)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_db_import_uses_typed_confirm():
    assert "await showTypedConfirm(" in HTML_TEMPLATE
    # the two odontogram prompts are intentionally deferred (chart is hidden)
    assert HTML_TEMPLATE.count("prompt(") == 2, "expected exactly the 2 deferred odontogram prompts"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_db_import_uses_typed_confirm -q`
Expected: FAIL (3 `prompt(` present).

- [ ] **Step 3: Replace the DB-import guard** (~line 6080):

```javascript
// OLD
            const typed = prompt(warn + '\\n\\nType ' + verb + ' to confirm:');
            if (typed !== verb) return;
// NEW
            const okTyped = await showTypedConfirm({ message: warn, word: verb, confirmLabel: verb === 'REPLACE' ? t('replace_data', 'Replace data') : t('merge_data', 'Merge data') });
            if (!okTyped) return;
```

Add the two button-label keys. **EN** dict:
```javascript
                replace_data: 'Replace data',
                merge_data: 'Merge data',
```
**AR** dict:
```javascript
                replace_data: 'استبدال البيانات',
                merge_data: 'دمج البيانات',
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_db_import_uses_typed_confirm -q`
Expected: PASS.

- [ ] **Step 5: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add templates.py
git commit -m "feat(ui-p2): DB import replace/merge guard uses showTypedConfirm"
```

---

### Task 7: Migrate the 33 `alert()` calls to `showToast()`

Rule: `alert(MSG)` → `showToast(MSG, KIND)`, where `KIND` is by intent — **failures** (`save_failed`, `Delete failed`, `Sync failed`, `Could not reach…`, `unable_*`, `Patient data not loaded`, `no_entry_found`) → `'error'`; **validation** (`fill_all_fields`, `*_required`, `password_too_short`, `passwords_do_not_match`, `select_patient_first`, `invoice_preview_unavailable`, `Activate license first`, `Sync did not complete`) → `'warning'`; **success** (`password_changed`, `procedure_saved`, `visit_started`, `Synced …`) → `'success'`; **neutral** (`no_patient_match`) → `'info'`.

**Files:**
- Modify: `templates.py` (all remaining `alert(` call sites)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_no_native_alert_remains():
    assert HTML_TEMPLATE.count("alert(") == 0, "a native alert( call (or comment) still remains"

def test_alert_messages_now_toast():
    # representative former-alert messages now route through showToast
    assert "showToast(t('save_failed', 'Save failed'), 'error')" in HTML_TEMPLATE
    assert "showToast(t('password_changed', 'Password changed successfully.'), 'success')" in HTML_TEMPLATE
    assert HTML_TEMPLATE.count("showToast(") >= 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_no_native_alert_remains tests/test_ui_phase2.py::test_alert_messages_now_toast -q`
Expected: FAIL.

- [ ] **Step 3: Enumerate and convert.** List every remaining site:

Run: `grep -n "alert(" templates.py`

Convert each per the KIND rule. Representative transformations (apply the same shape to every site — the argument inside `alert(...)` is copied verbatim as the first arg to `showToast`, the KIND is added as the second):

```javascript
// error (most common)
if (!resp.ok) { alert(t('save_failed','Save failed')); return; }
// →
if (!resp.ok) { showToast(t('save_failed', 'Save failed'), 'error'); return; }

// validation
alert(t('fill_all_fields', 'Please fill in all fields.')); return;
// →
showToast(t('fill_all_fields', 'Please fill in all fields.'), 'warning'); return;

// success
alert(t('password_changed', 'Password changed successfully.'));
// →
showToast(t('password_changed', 'Password changed successfully.'), 'success');

// bilingual inline string (e.g. the sync handlers ~6346-6361) keep the expression, add kind
alert(_ar() ? 'فشل المزامنة' : 'Sync failed');
// →
showToast(_ar() ? 'فشل المزامنة' : 'Sync failed', 'error');
```

Work top-to-bottom through the grep list. After converting, re-run `grep -n "alert(" templates.py` and confirm **zero** matches (the obsolete comment was already removed in Task 4 Step 4).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_no_native_alert_remains tests/test_ui_phase2.py::test_alert_messages_now_toast -q`
Expected: PASS.

- [ ] **Step 5: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): migrate 33 alert() calls to showToast (by intent)"
```

---

### Task 8: Skeleton CSS

**Files:**
- Modify: `templates.py` (CSS, after the `.loading-state` rules ~line 1596)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_skeleton_css_present():
    assert ".skeleton" in HTML_TEMPLATE
    assert "@keyframes skeleton-sweep" in HTML_TEMPLATE
    assert "prefers-reduced-motion" in HTML_TEMPLATE
    assert ".skeleton-avatar" in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_skeleton_css_present -q`
Expected: FAIL.

- [ ] **Step 3: Add the CSS** after the `.loading-state` block (~line 1596):

```css
        /* ── Skeleton loading placeholders (shimmer; static under reduced-motion) ── */
        .skeleton {
            display: inline-block;
            background: var(--surface-border, rgba(15,23,42,.09));
            border-radius: 6px;
            position: relative;
            overflow: hidden;
        }
        .skeleton::after {
            content: '';
            position: absolute;
            inset: 0;
            transform: translateX(-100%);
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.45), transparent);
            animation: skeleton-sweep 1.3s ease-in-out infinite;
        }
        body[data-theme="dark"] .skeleton::after {
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.10), transparent);
        }
        .skeleton-bar { height: 12px; }
        .skeleton-avatar { width: 54px; height: 54px; border-radius: 50%; }
        .skeleton-tile { height: 54px; border-radius: 10px; flex: 1; }
        .skeleton-row td { padding: 12px 14px; }
        .profile-skeleton { display: flex; flex-direction: column; gap: 12px; padding: 8px 4px; }
        .profile-skeleton__head { display: flex; align-items: center; gap: 14px; margin-bottom: 6px; }
        .profile-skeleton__lines { display: flex; flex-direction: column; gap: 8px; flex: 1; }
        .profile-skeleton__tiles { display: flex; gap: 10px; }
        @keyframes skeleton-sweep { to { transform: translateX(100%); } }
        @media (prefers-reduced-motion: reduce) {
            .skeleton::after { animation: none; }
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_skeleton_css_present -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): skeleton CSS (shimmer + reduced-motion fallback)"
```

---

### Task 9: `renderSkeletonRows` + swap into the four table loaders

**Files:**
- Modify: `templates.py` (helper after `renderStateRow` ~line 4991; loaders at dashboard ~5003, patients ~5059, appointments ~5205, billing ~5646)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_skeleton_rows_helper_and_usage():
    assert "function renderSkeletonRows" in HTML_TEMPLATE
    # used in place of the text loading state for the four tables
    assert HTML_TEMPLATE.count("renderSkeletonRows(") >= 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_skeleton_rows_helper_and_usage -q`
Expected: FAIL.

- [ ] **Step 3: Add the helper** immediately after `renderStateRow` (~line 4991):

```javascript
        // Skeleton <tr>s shaped to a table's column count, used while data loads.
        function renderSkeletonRows(colSpan, rowCount) {
            const widths = ['72%', '54%', '84%', '46%', '64%'];
            const rows = rowCount || 5;
            let out = '';
            for (let r = 0; r < rows; r++) {
                let cells = '';
                for (let c = 0; c < colSpan; c++) {
                    const w = widths[(r + c) % widths.length];
                    cells += `<td><span class="skeleton skeleton-bar" style="width:${w}"></span></td>`;
                }
                out += `<tr class="skeleton-row" aria-hidden="true">${cells}</tr>`;
            }
            return out;
        }
```

- [ ] **Step 4: Swap the four loading states.** Replace each `renderStateRow(..., kind: 'loading')` (and the bare billing loader) with `renderSkeletonRows(colSpan)`.

Dashboard (~5003), colSpan 4:
```javascript
// OLD
                tbody.innerHTML = renderStateRow(t('loading', 'Loading...'), {
                    icon: '⏳',
                    title: t('loading_dashboard', 'Loading dashboard data...'),
                    text: t('loading_dashboard_hint', 'Refreshing totals and recent appointments.'),
                    colSpan: 4,
                    kind: 'loading'
                });
// NEW
                tbody.innerHTML = renderSkeletonRows(4);
```

Patients (~5059), colSpan 9:
```javascript
// OLD
                tbody.innerHTML = renderStateRow(t('loading', 'Loading...'), {
                    icon: '⏳',
                    title: t('loading_patients', 'Loading patients...'),
                    text: t('loading_patients_hint', 'Fetching the patient list.'),
                    colSpan: 9,
                    kind: 'loading'
                });
// NEW
                tbody.innerHTML = renderSkeletonRows(9);
```

Appointments (~5205): use the `colSpan` value present at that call site (copy the number from the existing `colSpan:` line) — replace the whole `renderStateRow(..., kind: 'loading')` assignment with `tbody.innerHTML = renderSkeletonRows(<thatColSpan>);`.

Billing (~5646):
```javascript
// OLD
            body.innerHTML = `<tr><td colspan="5">${t('loading', 'Loading…')}</td></tr>`;
// NEW
            body.innerHTML = renderSkeletonRows(5);
```

(Leave the `empty`/`error` `renderStateRow` calls unchanged — only the loading states become skeletons.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_skeleton_rows_helper_and_usage -q`
Expected: PASS.

- [ ] **Step 6: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): skeleton rows for dashboard/patients/appointments/billing loaders"
```

---

### Task 10: Patient-profile skeleton

**Files:**
- Modify: `templates.py` (helper after `renderSkeletonRows`; wire into `viewPatientProfile` ~line 6482)
- Test: `tests/test_ui_phase2.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_profile_skeleton_present_and_wired():
    assert "function renderProfileSkeleton" in HTML_TEMPLATE
    assert "renderProfileSkeleton()" in HTML_TEMPLATE   # called inside viewPatientProfile
    assert 'class="profile-skeleton"' in HTML_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_phase2.py::test_profile_skeleton_present_and_wired -q`
Expected: FAIL.

- [ ] **Step 3: Add the helper** after `renderSkeletonRows`:

```javascript
        function renderProfileSkeleton() {
            return `
                <div class="profile-skeleton" aria-hidden="true">
                    <div class="profile-skeleton__head">
                        <span class="skeleton skeleton-avatar"></span>
                        <div class="profile-skeleton__lines">
                            <span class="skeleton skeleton-bar" style="width:60%;height:16px"></span>
                            <span class="skeleton skeleton-bar" style="width:38%"></span>
                        </div>
                    </div>
                    <div class="profile-skeleton__tiles">
                        <span class="skeleton skeleton-tile"></span>
                        <span class="skeleton skeleton-tile"></span>
                        <span class="skeleton skeleton-tile"></span>
                    </div>
                    <span class="skeleton skeleton-bar" style="width:90%"></span>
                    <span class="skeleton skeleton-bar" style="width:80%"></span>
                    <span class="skeleton skeleton-bar" style="width:86%"></span>
                </div>
            `;
        }
```

- [ ] **Step 4: Wire it in.** At the **top** of `viewPatientProfile(patientId)` body (immediately after the `async function viewPatientProfile(patientId) {` line, ~6482), insert — using inline `getElementById` (do **not** declare `const content`, that name is already declared later at ~6490):

```javascript
            const _profileContent = document.getElementById('patient-profile-content');
            const _profileModal = document.getElementById('patient-profile-modal');
            if (_profileContent) _profileContent.innerHTML = renderProfileSkeleton();
            if (_profileModal) _profileModal.classList.add('active');
```

(The existing `content.innerHTML = ...` at ~6507 then replaces the skeleton with the real profile; the existing `.classList.add('active')` at ~6664 is now a harmless no-op.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_phase2.py::test_profile_skeleton_present_and_wired -q`
Expected: PASS.

- [ ] **Step 6: Render sweep**

Run: `python -c "import templates; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add templates.py tests/test_ui_phase2.py
git commit -m "feat(ui-p2): patient-profile skeleton on profile open"
```

---

### Task 11: Full verification (suite + render sweep + Playwright smoke)

**Files:** none (verification only)

- [ ] **Step 1: Full pytest suite**

Run: `python -m pytest tests/ -q`
Expected: exit 0 (`$LASTEXITCODE` / `echo $?` == 0). No existing test regressed; all `tests/test_ui_phase2.py` tests pass.

- [ ] **Step 2: Final escaping/render sweep**

Run: `python -c "import templates; h=templates.HTML_TEMPLATE; assert h.count('alert(')==0 and h.count('confirm(')==0 and h.count('prompt(')==2; print('dialogs clean')"`
Expected: prints `dialogs clean`.

- [ ] **Step 3: Playwright behavioral smoke** (gated on a seeded active license — see `reference_web_visual_smoke` recipe: fresh temp DB, login admin/admin, force theme via `data-theme`). Drive the running portal and assert:
  - Trigger a delete (e.g. delete patient) → `#confirm-modal` becomes `.active`; clicking Cancel resolves false (no delete); re-trigger and confirm → delete proceeds.
  - With the modal open, press `Escape` → modal closes, no delete (resolves false).
  - DB import replace → typed-confirm modal shows; OK is disabled until `REPLACE` is typed, enabled after.
  - Open a patient profile → `.profile-skeleton` appears, then is replaced by real content.
  - Navigate to patients/dashboard → `.skeleton-row`s appear during load, then real rows.
  - **Zero JS console errors** across the run.

- [ ] **Step 4: Commit (if Playwright produced any fixture/test artifacts; otherwise skip)**

```bash
git add -A
git commit -m "test(ui-p2): Playwright behavioral smoke for modal + skeletons"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Confirm modal (reuse `.modal`, promise API, danger/neutral/typed, a11y) → Tasks 2,3,4 ✓
- 6 `confirm()` migration → Task 5 ✓
- 1 typed `prompt()` migration → Task 6 ✓
- 33 `alert()` → toast → Task 7 ✓
- Skeleton table loader (4 tables) → Tasks 8,9 ✓
- Patient-profile skeleton → Tasks 8,10 ✓
- i18n EN+AR → Tasks 1,6 ✓
- Tests (pytest sentinels + regression counts + Playwright + render sweep) → every task + Task 11 ✓
- Deferred odontogram prompts (count stays 2) → asserted in Tasks 6 & 11 ✓

**Placeholder scan:** No TBD/TODO; all code blocks are concrete; the 33-alert task gives the rule + representative transforms + a `count==0` enforcing test rather than 33 blind diffs (the message expression is copied verbatim, KIND appended).

**Type/name consistency:** `showConfirm`, `showTypedConfirm`, `_openConfirm`, `_closeConfirm`, `_confirmKeydownHandler`, `_confirmResolver`, `_confirmLastFocus`, `renderSkeletonRows`, `renderProfileSkeleton`, classes `.confirm-modal__ok/__cancel/__input/__hint/__icon/__msg/__typed`, `.skeleton`/`.skeleton-bar`/`.skeleton-avatar`/`.skeleton-tile`/`.skeleton-row`/`.profile-skeleton` — all used consistently across CSS, markup, controller, and tests.
