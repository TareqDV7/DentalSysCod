# Licensing overhaul — B: Premium First-Run Onboarding — design

## Goal

Make first run feel **premium and effortless** — one credential, no URLs, no jargon:

- **Desktop:** the operator pastes the **serial once**. That single action activates the license
  (A2/A3) and, with **one tap**, also links the clinic to the cloud for backup — because the cloud
  URL is **baked into the build** (never typed). Activation and cloud-link are one guided flow, not
  two disconnected settings.
- **Mobile:** the phone **scans the desktop's QR** (or auto-pairs over Bluetooth — existing
  mechanics) and is immediately usable. It **never types a serial or a URL**; it **derives** its
  license state from the desktop's `/api/license/gate` over the LAN. The desktop is the authority.

B is the *experience* wrapper over A1–A3's machinery: baked URL, collapsed activation+link, and a
mobile gate that reflects the desktop.

## Initiative context

Fourth of the five licensing sub-projects (map in
`docs/superpowers/specs/2026-06-03-licensing-a1-cloud-authority-design.md`). Depends on:

- **A2** — trustworthy `/api/license/activate` + `_license_cloud_url()` (env → paired → None).
- **A3** — `GET /api/license/gate` + the first-run activation overlay it consumes.

Build order: **A1 ✅ → A2 → A3 → B (this) → C**.

### Locked decisions carried into B

- **Serial once, no URL typing.** The owner's premium-onboarding requirement. The cloud URL is a
  product constant, not operator input. (Brainstorming, 2026-06-03.)
- **Desktop is the authority; mobile derives over LAN.** Mobile's license screen is a *reflection*
  of the desktop's gate — the phone makes no independent cloud license call. (Confirmed by the
  user, 2026-06-03.)
- **Validation decoupled from cloud-save.** One-tap cloud link is **optional and explicit** — the
  clinic can activate and run fully offline forever and never link to the cloud. Linking is a
  deliberate second tap, surfaced but never automatic. (A1 locked decision #6.)

## Existing mechanics (build on, do not break)

- **`_license_cloud_url()`** (A2) → `env CLINIC_LICENSE_CLOUD_URL → _cloud_sync_config()[0] → None`.
  B adds the final fallback: **→ `_BAKED_CLOUD_BASE_URL`**.
- **`POST /api/cloud/pair`** (`dental_clinic.py:4445`) already links the clinic: it accepts
  `{cloud_url?, serial_number, offline_token?}`, registers with the cloud, stores `cloud_url`
  /`cloud_clinic_token`, and does a first sync. `cloud_url` may be omitted when `CLINIC_CLOUD_URL`
  env is set. **B extends the omitted case to fall back to `_BAKED_CLOUD_BASE_URL`**, so a one-tap
  link needs only the serial the operator already entered.
- **`_resolve_offline_token(data)`** (`~:355`) finds the signed token to forward to the cloud's
  Ed25519 gate during pairing. The A3 activation already holds the vendor `serial_token`
  (persisted as `active_serial_token` in A3/T5), so one-tap link can re-use it.
- **A3 activation overlay** (`templates.HTML_TEMPLATE`, `id="license-gate-overlay"`) is the
  serial-entry surface. **B adds the post-activation "link to cloud" step to the same overlay.**
- **Cloud-pairing QR** `GET /api/cloud/pairing-qr` (`:4523`) renders `{v:1, u:cloud_url,
  t:clinic_token}` as SVG. **Mobile already parses this** (`pairing_payload.dart`,
  `parsePairingPayload`). B does **not** change the QR format.
- **LAN device pairing** (`/api/pairing/start` + `/api/pairing/complete`) returns a `device_token`;
  `PairingService` (Dart) drives it with a desktop `baseUrl`. Mobile already reaches the desktop
  over the LAN with that `baseUrl` + `device_token`.
- **Mobile HTTP:** `ApiClient.getJson({baseUrl, path, deviceToken})` (`api_client.dart:30`) — the
  exact call shape B's gate service uses against `/api/license/gate`.
- **Bluetooth zero-setup auto-pair** (shipped, `0dfdbf7`) already hands the phone a desktop LAN
  `baseUrl` with no typing — B's mobile onboarding sits on top of whatever delivered the `baseUrl`
  (BT auto-pair or scanned QR).

## B scope

**In (desktop / Python + template):**

1. **`_BAKED_CLOUD_BASE_URL`** constant + `_license_cloud_url()` fallback + `/api/cloud/pair`
   omitted-URL fallback. The operator never types a cloud URL.
2. **Collapsed onboarding** in the A3 overlay: after a successful activation, show a single
   **"Enable secure cloud backup"** button that calls `/api/cloud/pair` with the
   already-known serial (+ retained `active_serial_token`) and the baked URL — one tap, no URL,
   no second serial entry. A **"Not now"** keeps the clinic fully offline.
3. **`GET /api/onboarding/state`** — a tiny endpoint the SPA/mobile use to decide what to show:
   `{licensed_state, cloud_linked, needs_onboarding}`.

**In (mobile / Dart):**

4. **`LicenseGateState` model + `LicenseGateService.fetchGate(baseUrl, deviceToken)`** — calls the
   desktop `/api/license/gate` and maps it to a sealed Dart state.
5. **Mobile gate screen** that blocks the app when the desktop reports `unlicensed`/`view_only`
   and shows a renewal/“ask the clinic desktop” message — the phone never activates anything.

**Out:** the toggle-only sync collapse (**C** — B keeps the explicit one-tap link button; C turns
ongoing sync into a single switch); admin GUI (**D**); changing the QR or LAN-pairing protocols;
any new crypto.

## Desktop: baked cloud URL

```python
# Product constant: the vendor's cloud node base URL, baked into the build so the
# operator never types it. NOT a secret (it's a public endpoint). Override at
# runtime with CLINIC_LICENSE_CLOUD_URL / CLINIC_CLOUD_URL for staging/self-host.
_BAKED_CLOUD_BASE_URL = 'https://cloud.dentacare.app'   # vendor fills the real host
```

- `_license_cloud_url()` final chain: `env CLINIC_LICENSE_CLOUD_URL → paired cloud_url →
  _BAKED_CLOUD_BASE_URL`. So license validation works on a brand-new install with zero config.
- `/api/cloud/pair`: when `cloud_url` is omitted and `CLINIC_CLOUD_URL` env is unset, use
  `_BAKED_CLOUD_BASE_URL`. One-tap link body becomes just `{serial_number}` (+ the server
  attaches the retained `active_serial_token` via `_resolve_offline_token`).

## Desktop: collapsed activation → optional one-tap link

The A3 overlay gains a second panel, shown only **after** activation succeeds:

```text
[ Activate ]  → POST /api/license/activate {serial_token}     (A2/A3)
   on success →
[ Enable secure cloud backup ]  → POST /api/cloud/pair {serial_number}   (baked URL)
[ Not now ]                     → close overlay, stay offline
```

`GET /api/onboarding/state` drives this:

```json
{ "licensed_state": "active|grace|view_only|unlicensed",
  "cloud_linked": true|false,
  "needs_onboarding": true|false }
```

- `cloud_linked` = both `cloud_url` and `cloud_clinic_token` present in `app_settings`.
- `needs_onboarding` = `licensed_state == 'unlicensed'` **or** (`licensed` and not `cloud_linked`
  and the operator hasn't dismissed the cloud nudge — a `app_settings['cloud_link_dismissed']`
  flag set by "Not now").

This keeps activation and cloud-link in one flow while preserving the decoupling: the link is a
separate, optional, explicitly-confirmed tap, and "Not now" is durably remembered.

## Mobile: derive over LAN

The phone already holds a desktop LAN `baseUrl` + `device_token` (from BT auto-pair or the LAN
pair-code flow). B adds, in pure Dart:

```dart
sealed class LicenseGateState { const LicenseGateState(); }
final class GateActive   extends LicenseGateState { const GateActive(); }
final class GateGrace    extends LicenseGateState { const GateGrace(this.graceUntil); final String graceUntil; }
final class GateViewOnly extends LicenseGateState { const GateViewOnly(); }
final class GateUnlicensed extends LicenseGateState { const GateUnlicensed(); }
final class GateUnknown  extends LicenseGateState { const GateUnknown(); } // desktop unreachable
```

`LicenseGateService.fetchGate(baseUrl, deviceToken)` GETs `/api/license/gate` via
`ApiClient.getJson` and maps `state` → the sealed type; a network error → `GateUnknown` (the phone
stays usable offline — it never *gates itself* on a transient LAN hiccup, only on an explicit
desktop `view_only`/`unlicensed`). A pure `mapGateState(Map json)` function does the mapping so it
is unit-testable without a server.

**Mobile gate screen behaviour** (mirrors the desktop, friendlier copy):

| Desktop state | Mobile screen |
| --- | --- |
| `active` | normal app |
| `grace` | dismissible "Renew on the clinic desktop by `<date>`" banner |
| `view_only` | read-only mode + "Ask the clinic to renew the license" notice |
| `unlicensed` | "This clinic isn't activated yet — activate on the desktop first" block |
| unreachable | normal app (offline-tolerant), silent retry |

The phone never shows a serial field — onboarding on mobile is *scan/auto-pair → use*.

## Error handling

- `/api/onboarding/state` and `/api/license/gate` are reads → deterministic JSON, never `500`.
- One-tap link reuses `/api/cloud/pair`, which already returns `502` on a cloud-unreachable error
  with a clean message — B surfaces that inline in the overlay ("Couldn't reach the cloud — you
  can enable backup later in Settings") without blocking activation. **Activation success is never
  contingent on the cloud link succeeding.**
- Mobile `fetchGate` maps any `DioException` → `GateUnknown`; the app stays usable.

## Security / product notes

- `_BAKED_CLOUD_BASE_URL` is **not a secret** — it's a public endpoint. Baking it is a UX choice,
  not a security one. Staging/self-host override via env.
- One-tap link forwards the **vendor-signed** `active_serial_token` (not a secret beyond the serial
  itself) so the cloud's `CLINIC_REQUIRE_SIGNED_SERIAL=1` gate accepts the registration.
- The phone deriving over LAN means a lost/stolen phone loses access the moment the desktop marks
  it `view_only`/revokes its device slot — no independent mobile license to revoke separately.

## Test plan (B)

**Backend (`tests/test_onboarding_b.py`, local mode):**
- `_license_cloud_url()` returns `_BAKED_CLOUD_BASE_URL` when no env/paired URL is set; env and
  paired URL still win over the baked default (precedence order).
- `/api/cloud/pair` with `cloud_url` omitted and no env → attempts the baked URL (stub
  `_cloud_http_request` to assert the URL it was called with), and still writes `cloud_url`
  = baked on success.
- `GET /api/onboarding/state`: fresh install → `{needs_onboarding:true, cloud_linked:false}`;
  after a seeded active license but unlinked → `needs_onboarding:true, cloud_linked:false`; after
  seeding `cloud_url`+`cloud_clinic_token` → `cloud_linked:true`; after `cloud_link_dismissed`
  → `needs_onboarding:false` (licensed + dismissed).
- Decoupling: a successful activation **without** tapping link leaves `cloud_url` unset
  (re-asserts the A3 invariant through the B flow).

**Frontend (`tests/test_onboarding_ui_b.py`, template presence + JS sweep):**
- `HTML_TEMPLATE` contains the cloud-link button id (e.g. `id="license-link-cloud"`), the "Not
  now" control, and a `fetch('/api/cloud/pair'` call; `node --check` JS sweep passes.

**Mobile (`clinic_mobile_app/test/license_gate_service_test.dart`, pure Dart):**
- `mapGateState({'state':'active'})` → `GateActive`; `grace` → `GateGrace(graceUntil)`;
  `view_only` → `GateViewOnly`; `unlicensed` → `GateUnlicensed`; unknown/missing → `GateUnknown`.
- `fetchGate` with a fake `ApiClient` returning a gate map → the mapped state; a thrown
  `ApiException` → `GateUnknown`.
- `dart analyze` clean; `flutter test` green.

## Dependencies

None new on the backend. Mobile reuses `dio` via the existing `ApiClient`; the gate service and
sealed state are pure Dart (no new packages). No QR/crypto changes.

## Deferred / open

- **Toggle-only ongoing sync** (one switch that owns pairing + periodic sync) → **C**. B leaves the
  explicit one-tap link button; C subsumes it into the toggle.
- **In-app self-serve renewal/payment** is out of the whole initiative — renewal = present a fresh
  vendor serial on the desktop.
- **Auto-discovery of the desktop `baseUrl`** is owned by the BT zero-setup initiative, not B; B
  assumes the phone already has a `baseUrl` + `device_token`.
