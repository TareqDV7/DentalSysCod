# Licensing overhaul — C: Toggle-Only Auto Cloud Sync — design

## Goal

Collapse the multi-field **Cloud Sync** settings (URL input + serial input + Pair button + Sync-
now / Link-phone / Unpair) into a **single toggle**: *Cloud backup — On / Off*. Flipping it on
links this clinic to the cloud using the **baked URL** (B) and the **already-activated serial**
(A2/A3) — **no typing** — and ongoing sync runs automatically in the background. Flipping it off
unpairs and stops. Same plumbing underneath; one switch on top.

## Initiative context

Fifth shippable layer (map in
`docs/superpowers/specs/2026-06-03-licensing-a1-cloud-authority-design.md`). Depends on:

- **B** — `_BAKED_CLOUD_BASE_URL` + `/api/cloud/pair` working with just a serial.
- **A2/A3** — `active_serial_number` + retained `active_serial_token` (the serial the toggle uses
  automatically).

Build order: **A1 ✅ → A2 → A3 → B → C (this)**. C is the UX capstone of the cloud-sync story.

### Locked decisions carried into C

- **Toggle-only.** The owner wants cloud sync to be a single on/off, not a form. (Brainstorming,
  2026-06-03.)
- **Validation decoupled from cloud-save.** The toggle controls **sync only** — turning it off
  never affects the license (the clinic stays licensed and fully usable offline). Turning it on
  never changes license state. (A1 locked decision #6.)
- **Mirror the existing BT toggle.** Bluetooth sync already uses a single `bt-toggle-row` switch
  (`templates.py:2443`); cloud sync should match it for consistency.

## Existing mechanics (build on, do not break)

- **`POST /api/cloud/pair`** (`dental_clinic.py:4445`) — registers with the cloud, stores
  `cloud_url`/`cloud_clinic_token`/`cloud_clinic_id`, runs a first sync. B made `cloud_url`
  optional (baked fallback). It still expects a `serial_number` in the body.
- **`POST /api/cloud/unpair`** (`:4580`) — deletes the cloud_* `app_settings` keys (the OFF path).
- **`GET /api/cloud/status`** (`:4498`) — returns `{configured, cloud_url, last_sync_*, …}`.
  `configured == (cloud_url and cloud_clinic_token)` is the **toggle's on/off source of truth**.
- **`POST /api/cloud/sync-now`** (`:4570`) — manual sync; kept as a small secondary action.
- **`GET /api/cloud/pairing-qr`** (`:4523`) — "Link a phone" QR; kept.
- **Background sync worker** `cloud_sync_worker` (`:6098`) already runs on a timer **only when
  `configured`**, so once the toggle pairs, ongoing sync is automatic with no further UI.
- **`active_serial_number`** (`app_settings`) is the activated serial; A3/T5 also retains
  `active_serial_token` (the vendor-signed token) so the toggle can pair with **zero inputs**.
- **`_resolve_offline_token(data)`** (`~:355`) — finds the signed token to forward to the cloud's
  Ed25519 gate; C falls back to the retained `active_serial_token` when the body carries none.
- **UI to collapse:** `templates.py:2405-2434` (the Cloud Sync section) + its JS
  `loadCloudSyncSettings`/`cloudPair`/`cloudSyncNow`/`cloudUnpair`/`cloudShowPairingQr`
  (`:5584-5679`). The BT toggle markup at `:2443` is the visual template to copy.

## C scope

**In:**

1. **`POST /api/cloud/enable`** — a zero-input "pair using what we already know": reads
   `active_serial_number` (+ `active_serial_token`), resolves the baked/configured URL, and runs the
   same register-then-first-sync as `cloud_pair`. No license activation happens here (sync only).
2. **Refactor** the body of `cloud_pair` into a shared `_link_clinic_to_cloud(cloud_url, serial,
   offline_token)` helper so `cloud_pair` and `cloud_enable` share one implementation (DRY).
3. **Toggle UI** — replace the URL+serial pair form and the three paired-action buttons with one
   `cloud-toggle-row` switch (mirroring `bt-toggle-row`). Keep the status line, the dashboard badge,
   "Link a phone" QR, and a small "Sync now" shown only when on.
4. **Tests** (backend + template presence + JS sweep).

**Out:** changing the sync protocol, interval, or worker; the BT toggle; anything license-state-
related (C is sync-only). No mobile change (mobile already auto-syncs once it has a desktop URL +
token; C is a desktop settings-UX collapse).

## Backend: `/api/cloud/enable` (zero-input toggle-on)

```text
POST /api/cloud/enable   (local server only)
  serial  = active_serial_number  (app_settings)
  token   = active_serial_token   (app_settings, retained at activation)
  url     = _license_cloud_url()  → baked/configured (B)
  if not serial → 409 { error: "Activate a license first", reason: "not_activated" }
  if not url    → 400 { error: "No cloud server configured" }
  → _link_clinic_to_cloud(url, serial, token)   # same as cloud_pair internals
  → { success, cloud_url, first_sync }
```

`_link_clinic_to_cloud(cloud_url, serial, offline_token)` is the extracted core of today's
`cloud_pair`: build the register body (with the signed token when present), call the cloud's
`/api/clinics/register`, persist `cloud_url`/`cloud_clinic_token`/`cloud_clinic_id`, run
`_run_cloud_sync_once`, return the result dict (or an error tuple). `cloud_pair` keeps its current
request parsing and delegates to it; `cloud_enable` parses nothing and delegates to it.

**Decoupling invariant (tested):** `cloud_enable` reads the license state but never **writes** it;
`cloud_unpair` never touches `licenses`/`active_serial_number`. Toggling sync leaves the license
exactly as it was, and vice-versa.

## Frontend: one toggle

Replace `#cloud-pair-form` + `#cloud-paired-actions` button cluster with:

```html
<div class="cloud-toggle-row bt-toggle-row">
  <label>
    <input type="checkbox" id="cloud-enabled" onchange="cloudToggle(this.checked)"/>
    <span data-en="Cloud backup" data-ar="النسخ الاحتياطي السحابي">Cloud backup</span>
  </label>
</div>
<div id="cloud-secondary" style="display:none;margin-top:12px;">
  <button class="btn btn-secondary" type="button" onclick="cloudSyncNow(this)"
          data-en="Sync now" data-ar="مزامنة الآن">Sync now</button>
  <button class="btn btn-secondary" type="button" onclick="cloudShowPairingQr()"
          data-en="Link a phone" data-ar="ربط هاتف">Link a phone</button>
  <!-- existing #cloud-pairing-qr block stays here -->
</div>
```

Behaviour (`cloudToggle(checked)`):

- **checked** → `POST /api/cloud/enable`. On `409 not_activated` → revert the toggle and show
  "Activate a license first". On success → status line + secondary actions appear; the background
  worker takes over.
- **unchecked** → confirm, then `POST /api/cloud/unpair`; hide secondary actions.

`loadCloudSyncSettings` sets `#cloud-enabled.checked = st.configured` and shows `#cloud-secondary`
only when `configured`. The status line and badge keep their current rendering. `cloudPair` (the
old URL+serial form handler) is **removed**; `cloudSyncNow`/`cloudUnpair`/`cloudShowPairingQr`
stay. The `#cloud-url-input` / `#cloud-serial-input` fields are **deleted** — nothing to type.

## Error handling

- `/api/cloud/enable` mirrors `cloud_pair`'s clean errors: `409` (no license), `400` (no URL),
  `502` (cloud unreachable, from `_link_clinic_to_cloud`). Never `500`.
- A failed enable **reverts the toggle** so the UI never claims "on" when pairing failed.
- Offline / cloud-down on enable is a clear inline message, not a crash.

## Security / product notes

- `/api/cloud/enable` is a state-changing local endpoint behind the same portal login as the rest
  of settings; it exposes nothing new (it uses the already-stored serial/token).
- Toggling sync **off** does not delete cloud data — it stops mirroring. (Same as today's unpair.)

## Test plan (C)

**Backend (`tests/test_cloud_toggle_c.py`, local mode):**
- `POST /api/cloud/enable` with **no** active serial → `409 not_activated`.
- With `active_serial_number` (+ `active_serial_token`) seeded and `_cloud_http_request` stubbed to
  a successful register → pairs: asserts the register URL was the baked/configured base, and
  `cloud_url`/`cloud_clinic_token` are written; response `success:true`.
- `enable` forwards the retained `active_serial_token` as `offline_token` in the register body
  (assert via the stub) so the cloud's signed-serial gate is satisfied.
- `cloud_pair` still works unchanged (regression) — the refactor preserved behaviour.
- **Decoupling:** after `enable`, the `licenses` row / `active_serial_number` are unchanged; after
  `unpair`, they are unchanged.

**Frontend (`tests/test_cloud_toggle_ui_c.py`, presence + JS sweep):**
- `HTML_TEMPLATE` contains `id="cloud-enabled"`, `cloudToggle(`, and `fetch('/api/cloud/enable'`.
- The old typed-pairing inputs are gone: `id="cloud-url-input"` and `id="cloud-serial-input"` are
  **absent**; `function cloudPair(` is **absent**.
- `node --check` JS sweep passes (escaping trap guard).

## Dependencies

None new. Pure refactor + one endpoint + a UI collapse.

## Deferred / open

- A per-table or selective-sync UI is out of scope — the toggle is all-or-nothing, matching the
  current worker.
- Surfacing sync health beyond the existing badge/status line (e.g. a history panel) is a possible
  future polish, not part of C.
