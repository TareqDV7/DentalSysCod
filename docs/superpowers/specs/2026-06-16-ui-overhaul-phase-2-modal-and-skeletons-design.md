# UI Overhaul Phase 2 — Destructive-Action Modal + Skeleton Screens (Design)

**Date:** 2026-06-16
**Branch:** `feat/ui-overhaul-p2` (off `main`, which includes Phase 0 PR #8 and Phase 1 PR #9)
**Phase:** 2 of the UI/UX Overhaul (4-phase plan; see prior phase specs in this directory) — "no more native browser dialogs" + content-shaped loading.
**Status:** Approved design (brainstormed via superpowers + visual companion, 2026-06-16).

---

## 1. Problem

The desktop app (Flask, single `templates.py`) still uses **42 native browser dialogs** — `alert()`, `confirm()`, `prompt()`. Native dialogs are jarring, unstyled, block the JS thread, ignore the Editorial Slate design language shipped in Phase 0, and cannot be themed or localized consistently. Separately, async data loads show a plain text "Loading patients…" message, which reads as a stall rather than progress.

An in-code comment (added in the pre-overhaul batch, `templates.py` ~line 3975) already set the intended direction: *new code should call `showToast()` instead of `alert()`; blocking `confirm()`/`prompt()` stay until "the modal sweep."* This phase **is** that sweep, plus skeleton screens.

## 2. Goals / Non-Goals

**Goals**
- Replace all **7 destructive** native dialogs (6 `confirm()` + 1 typed `prompt()`) with a designed, themed, localized **confirm modal**.
- Convert the **33 informational `alert()`** calls to the existing `showToast()` primitive.
- Add **skeleton screens** to the shared table loader (dashboard, patients, appointments, billing) and the patient-profile load.
- End state: **zero native dialogs** reachable in the live app.

**Non-Goals**
- The **2 odontogram `prompt()`** calls (`templates.py` ~6897/6899). The odontogram is hidden (dead code) — these belong to Phase 3.
- Skeletons on low-traffic surfaces (accounts/receivables, reports, settings audit log). Deferrable follow-up.
- Mobile (Flutter) — it has its own native dialog UX; out of scope.
- Any change to server/API/DB.

## 3. Inventory (the triage)

| Bucket | Count | Native call | Target |
|---|---|---|---|
| Informational | 33 | `alert()` | `showToast(msg, kind)` |
| Destructive yes/no | 6 | `confirm()` | `showConfirm({...})` |
| High-stakes guard | 1 | `prompt()` (type REPLACE/MERGE) | `showTypedConfirm({...})` |
| Deferred (hidden odontogram) | 2 | `prompt()` | **none** (Phase 3) |

The 6 `confirm()` sites: delete holiday (~5369), generic delete (~5708, ~7045), delete expense (~6033), clear catalogs (~6106), delete patient (~7472). The 1 typed `prompt()`: DB import replace/merge guard (~6080).

## 4. Existing infrastructure to build on

The app **already has a modal system** — the confirm modal reuses it rather than reinventing:
- `.modal` overlay (`display:none`; `.modal.active` → `display:flex`), backdrop `rgba(10,23,38,.58)`, `z-index:1000` (`templates.py` ~1073).
- `.modal-content` card: `#fff` (dark `#111a2b`), `border-radius:16px`, `--shadow`, themed for light/dark.
- `.modal-header h2`: Space Grotesk.
- `closeModal(id)` helper (~4811) and a **global `Escape` keydown handler** that removes `.active` from any open modal (~4815).
- Backdrop-click-to-close convention (inline `onclick` per modal).

Also available: `showToast(message, type, opts)` with `type ∈ {success,error,warning,info}` (~3990); design tokens `--surface`, `--surface-border`, `--accent #38bdf8`, `--accent-strong #1d7fb7`, `--accent-gradient`, `--danger #d9434e`, `--warning #d89e1f`, `--radius-xl 16px`, `--elev-raised`; the shared loading helper `renderStateRow(...)` with `kind:'loading'` (~4982) used by the dashboard/patients/appointments tables; a `.loading-state` style (~1596).

## 5. Design

### 5.1 Confirm modal

A **single reusable modal node**, injected into the DOM once, reusing the existing `.modal` / `.modal-content` / `.modal-header` classes (instant light/dark theme parity) plus a `.modal--confirm` modifier for the tighter confirm sizing (`max-width ~380px`) and the danger/neutral treatment.

**Public API (Promise-based):**

```js
// Resolves true on confirm, false on cancel/Esc/backdrop.
showConfirm({
  title,                 // string (required)
  message,               // string (required)
  confirmLabel,          // string, default t('confirm','Confirm') / t('delete','Delete') for danger
  cancelLabel,           // string, default t('cancel','Cancel')
  danger = true,         // true → red confirm button + warning icon; false → accent button + info icon
  icon,                  // optional override
}) // → Promise<boolean>

// Resolves true ONLY if the user types `word` exactly, then confirms.
showTypedConfirm({
  title, message,
  word,                  // e.g. 'REPLACE' | 'MERGE'
  confirmLabel,
}) // → Promise<boolean>
```

**Controller behavior:**
- Opens by setting `.active`; **default focus on Cancel** (safe default for destructive actions).
- **Focus trapped** while open (Tab cycles within the dialog); focus **restored** to the triggering element on close.
- Resolution: **`Esc` / backdrop click / Cancel → resolve(false)**; **`Enter` (when focus is not in the typed input) / Confirm button → resolve(true)**.
- The controller **owns its lifecycle** and resolves the promise itself, so it must coordinate with the existing global `Escape` handler: the confirm controller's own `Esc` path resolves(false) and closes; the global handler merely removing `.active` afterward is harmless (idempotent). No hung `await`.
- Only one confirm modal can be open at a time (programmatic, single instance).

**Variants & styling (Editorial Slate, solid card):**
- **Danger** (default, the common case): confirm button `background: var(--danger)` white text; icon = warning glyph (Phosphor warning if present in the P0 sprite, else an inline `⚠`/SVG) on a `rgba(217,67,78,.12)` tile.
- **Neutral**: confirm button `var(--accent-gradient)`; info icon. For future non-destructive yes/no (none today).
- **Typed-confirm**: adds a text `<input>`; confirm button stays **disabled** until `input.value.trim() === word`; helper line "Type **WORD** to confirm."
- Backdrop: the existing dim `rgba(10,23,38,.58)` (chrome may be glass/dim; the **card stays fully solid** — "glass for chrome, solid for data").

**Markup sketch (rendered once, hidden until invoked):**

```html
<div id="confirm-modal" class="modal modal--confirm" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
  <div class="modal-content">
    <div class="confirm-modal__icon" aria-hidden="true"><!-- warning/info --></div>
    <div class="modal-header"><h2 id="confirm-modal-title"></h2></div>
    <p class="confirm-modal__msg"></p>
    <div class="confirm-modal__typed" hidden>
      <input class="confirm-modal__input" type="text" autocomplete="off">
      <div class="confirm-modal__hint"></div>
    </div>
    <div class="confirm-modal__actions">
      <button type="button" class="btn confirm-modal__cancel"></button>
      <button type="button" class="btn confirm-modal__ok"></button>
    </div>
  </div>
</div>
```

### 5.2 Migration of call sites

- **`alert(x)` → `showToast(x, kind)`** (33 sites). `kind` mapped by intent: failures (`Save failed`, `Delete failed`, `Could not reach the server`) → `'error'`; validation (`Please pick a date`, `fill_all_fields`) → `'warning'`; success (`password_changed`, `visit_started`) → `'success'`; neutral info → `'info'`.
- **`if (!confirm(msg)) return;` → `if (!(await showConfirm({title, message: msg, ...}))) return;`** (6 sites). Each enclosing handler must be `async`. Most delete handlers already `await fetch(...)` (already async); the few that aren't get `async` added (and any caller relying on a sync return is checked). Titles/messages reuse existing i18n keys where present.
- **DB import `prompt(...)` → `await showTypedConfirm({word: verb, ...})`** (1 site, ~6080), preserving the existing REPLACE/MERGE semantics.

### 5.3 Skeleton screens

- **Shared table loader:** extend the existing loading path (`renderStateRow` / `kind:'loading'`) so it renders **N skeleton rows shaped to the table's columns** instead of the text message. One change covers dashboard / patients / appointments. Migrate the billing table's bare ``<tr><td colspan=5>Loading…</td></tr>`` (~5646) onto the same helper.
- **Patient profile:** show a skeleton block (avatar circle + name bar + line bars + stat tiles) inside the `patient-profile-modal` body while the profile fetch is in flight; replace with real content on resolve.
- **Style:** soft "bone" bars (a neutral fill derived from `--surface`/`--surface-border`) with a `translateX` shimmer sweep (`.skeleton` + `::after` gradient, `@keyframes`). **`@media (prefers-reduced-motion: reduce)` → no animation** (static bars). Skeleton containers carry `aria-hidden="true"` (decorative); the live region / status text continues to announce loading for SR users.

## 6. Internationalization

- Modal titles/messages reuse existing keys where they exist (`confirm_delete`, `delete_expense_confirm`, `delete_holiday_confirm`, `confirm_delete_patient`, the clear-catalogs message, etc.).
- New keys (EN + AR): confirm/cancel/`delete` labels as needed (`cancel`/`confirm` already exist; add `delete` if missing), typed-confirm hint (`type_to_confirm` with a `{word}` substitution), and a skeleton/loading `aria-label`.
- Toast conversions reuse the existing alert message keys verbatim — no new strings, just a different sink.

## 7. Testing

**pytest (substring sentinels, repo style — `tests/test_ui_phase2.py`):**
- `.modal--confirm` and danger/typed CSS present; `#confirm-modal` markup with `role="dialog"`/`aria-modal`.
- `showConfirm`, `showTypedConfirm`, and the skeleton render function names present.
- Skeleton CSS classes + the `prefers-reduced-motion` block present.
- New i18n keys present in **both** EN and AR.
- **Regression guard:** assert no `confirm(`, bare `alert(`, or `prompt(` remain at the migrated line regions (allow the 2 deferred odontogram prompts).
- Full suite (`pytest tests/`) exits 0 — no existing behavior changed.

**Playwright behavioral smoke (gated on a seeded active license):**
- `showConfirm` resolves true on confirm, false on Cancel and on `Esc`.
- Typed-confirm: confirm button disabled until the exact word is typed.
- A delete flow shows the modal and only proceeds on confirm.
- A skeleton appears during a data load and is replaced by real rows/content.
- **Zero JS console errors.**

**`templates.py` JS-escaping render sweep** — `HTML_TEMPLATE` is a normal Python string, so a bare `'\n'` in inline JS collapses to a real newline and breaks the whole `<script>`. This phase adds real inline JS; verify the template renders without breaking it (regex double-escaped as `\\d`/`\\.`; no bare `'\n'`; template literals use `${...}`, not Jinja `{{`).

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Sync handler can't `await showConfirm` | Audit each of the 6 confirm sites; add `async` where needed; verify no caller depends on a sync boolean return. |
| Global `Esc` handler double-handles | Confirm controller resolves(false) on its own `Esc`; global removing `.active` is idempotent. Verify with Playwright. |
| Backdrop click → accidental confirm | Backdrop and `Esc` always resolve **false**; only the explicit Confirm button / `Enter` resolve true. |
| JS-escaping trap breaks all buttons | Render sweep in the verification task; double-escape regex; no bare `'\n'`. |
| Skeleton flash on fast loads | Acceptable; skeleton replaces the existing text-loading state which had the same timing. No artificial min-delay. |

## 9. Out of scope (explicit)

- 2 odontogram `prompt()` calls (Phase 3).
- Skeletons for accounts/receivables, reports, audit log.
- Mobile Flutter dialogs.
- Server/API/DB changes.

## 10. Delivery

All changes in `templates.py` + one new test file. Built task-by-task (TDD where practical) under subagent-driven development, per-task spec + code-quality review, final holistic review, then PR to `main` (stacked conceptually on P0/P1, branched off merged main). User-side exe rebuild follows merge.
