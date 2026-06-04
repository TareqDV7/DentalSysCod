# Licensing B — Premium First-Run Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One credential, no URLs. The desktop operator pastes the serial once → activates → one optional tap links cloud backup using a baked URL. The phone scans/auto-pairs and derives its license state from the desktop over the LAN — never typing a serial or URL.

**Architecture:** A `_BAKED_CLOUD_BASE_URL` constant becomes the final fallback in `_license_cloud_url()` and `/api/cloud/pair`. The A3 activation overlay gains a post-activation one-tap cloud-link step driven by a new `GET /api/onboarding/state`. On mobile, a pure-Dart `LicenseGateService` + sealed `LicenseGateState` reflect the desktop's `/api/license/gate`.

**Tech Stack:** Python 3.12, Flask, SQLite; vanilla JS in `templates.HTML_TEMPLATE`; Dart/Flutter (`dio` via existing `ApiClient`). Tests: `pytest` (+ `node --check`) and `flutter test` / `dart analyze`.

**Spec:** `docs/superpowers/specs/2026-06-04-licensing-b-onboarding-design.md`
**Depends on:** A2 (`_license_cloud_url`, retained `active_serial_token`), A3 (`/api/license/gate`, activation overlay).

---

## File Structure

- **Modify** `dental_clinic.py`:
  - `_BAKED_CLOUD_BASE_URL` constant near `_license_cloud_url` (A2 helper region, `~:585`).
  - `_license_cloud_url()` fallback chain (add baked default).
  - `cloud_pair` (`:4445`) omitted-URL fallback to the baked default.
  - new `GET /api/onboarding/state` near `license_gate` (A3, `~:5025`).
- **Modify** `templates.py` (`HTML_TEMPLATE`): post-activation cloud-link panel + "Not now".
- **Create** mobile `clinic_mobile_app/lib/services/license_gate_service.dart` + the sealed `LicenseGateState`.
- **Create** tests: `tests/test_onboarding_b.py`, `tests/test_onboarding_ui_b.py`, `clinic_mobile_app/test/license_gate_service_test.dart`.
- **Update** `README.md` test-count line.

## Conventions

Backend: `rtk proxy python -m pytest tests/test_onboarding_b.py -v` — check `$LASTEXITCODE`.
Mobile: `rtk proxy dart analyze` and `rtk proxy flutter test test/license_gate_service_test.dart` from `clinic_mobile_app/` (use `rtk dart`/`rtk flutter`; failures only). The RTK note about `python -m pytest` does not apply to Dart.

---

### Task 1: Baked cloud URL + `_license_cloud_url` fallback

**Files:**
- Modify: `dental_clinic.py` (`_license_cloud_url`, add `_BAKED_CLOUD_BASE_URL`)
- Create: `tests/test_onboarding_b.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_onboarding_b.py
import sqlite3
import pytest
import dental_clinic


@pytest.fixture()
def local(tmp_path, monkeypatch):
    db = str(tmp_path / 'clinic.db')
    monkeypatch.setattr(dental_clinic, 'CLOUD_MODE', False)
    monkeypatch.setattr(dental_clinic, 'DB_NAME', db)
    monkeypatch.delenv('CLINIC_LICENSE_CLOUD_URL', raising=False)
    monkeypatch.delenv('CLINIC_CLOUD_URL', raising=False)
    dental_clinic.init_database()
    with dental_clinic.app.test_client() as c:
        yield c


def test_license_cloud_url_falls_back_to_baked(local):
    assert dental_clinic._license_cloud_url() == dental_clinic._BAKED_CLOUD_BASE_URL.rstrip('/')


def test_env_overrides_baked(local, monkeypatch):
    monkeypatch.setenv('CLINIC_LICENSE_CLOUD_URL', 'https://staging.example.test/')
    assert dental_clinic._license_cloud_url() == 'https://staging.example.test'
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_onboarding_b.py -k cloud_url -v`
Expected: FAIL — `_license_cloud_url()` currently returns `None` (no baked fallback); `_BAKED_CLOUD_BASE_URL` undefined.

- [ ] **Step 3: Implement**

Add the constant just above `_license_cloud_url` (defined in A2):

```python
# Product constant: vendor cloud node base URL, baked so the operator never types
# it. NOT a secret (public endpoint). Override via CLINIC_LICENSE_CLOUD_URL /
# CLINIC_CLOUD_URL for staging or self-host.
_BAKED_CLOUD_BASE_URL = 'https://cloud.dentacare.app'   # vendor: set the real host
```

Extend `_license_cloud_url` (A2) to fall back to it:

```python
def _license_cloud_url():
    url = os.environ.get('CLINIC_LICENSE_CLOUD_URL', '').strip()
    if not url:
        url = _cloud_sync_config()[0] or ''
    if not url:
        url = _BAKED_CLOUD_BASE_URL
    return (url.rstrip('/') or None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_onboarding_b.py -k "cloud_url or env_overrides" -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_onboarding_b.py
rtk git commit -m "feat(license): B bake cloud URL as the final _license_cloud_url fallback"
```

---

### Task 2: `/api/cloud/pair` omitted-URL → baked default (one-tap link)

**Files:**
- Modify: `dental_clinic.py:4453` (`cloud_pair`)
- Test: `tests/test_onboarding_b.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pair_uses_baked_url_when_omitted(local, monkeypatch):
    calls = {}
    def fake_http(method, url, headers=None, body=None, timeout=15):
        calls['url'] = url
        return 200, {'clinic_token': 'tok-123', 'clinic_id': 7}
    monkeypatch.setattr(dental_clinic, '_cloud_http_request', fake_http)
    monkeypatch.setattr(dental_clinic, '_run_cloud_sync_once', lambda *a, **k: {'ok': True})
    r = local.post('/api/cloud/pair', json={'serial_number': 'DENTAL-B-LINK1'})
    assert r.status_code == 200
    assert calls['url'].startswith(dental_clinic._BAKED_CLOUD_BASE_URL)
    # And it persisted the baked URL as the clinic's cloud_url.
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    val = conn.execute("SELECT value FROM app_settings WHERE key='cloud_url'").fetchone()[0]
    conn.close()
    assert val == dental_clinic._BAKED_CLOUD_BASE_URL.rstrip('/')
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_onboarding_b.py -k pair_uses_baked -v`
Expected: FAIL — current `cloud_pair` returns `400 cloud_url is required` when `cloud_url` is omitted and the env var is unset.

- [ ] **Step 3: Implement**

In `cloud_pair` (`:4453`), change the `cloud_url` resolution line:

```python
    cloud_url = str(data.get('cloud_url') or os.environ.get('CLINIC_CLOUD_URL') or '').strip().rstrip('/')
```

to fall back to the baked default:

```python
    cloud_url = str(data.get('cloud_url') or os.environ.get('CLINIC_CLOUD_URL')
                    or _BAKED_CLOUD_BASE_URL or '').strip().rstrip('/')
```

The existing `if not cloud_url:` guard stays (covers a vendor who sets the baked constant to '').

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_onboarding_b.py -k pair_uses_baked -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_onboarding_b.py
rtk git commit -m "feat(license): B one-tap cloud link uses the baked URL when omitted"
```

---

### Task 3: `GET /api/onboarding/state`

**Files:**
- Modify: `dental_clinic.py` (add route after `license_gate`, `~:5025`)
- Test: `tests/test_onboarding_b.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timedelta, timezone


def _seed_active_license(serial='DENTAL-B-ONB'):
    today = datetime.now(timezone.utc).date()
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute('''INSERT INTO licenses (serial_number, clinic_name, plan_name, status,
                    max_devices, expires_at, grace_until) VALUES (?,?,?,?,?,?,?)''',
                 (serial, 'C', 'standard', 'active', 3,
                  (today + timedelta(days=365)).strftime('%Y-%m-%d'),
                  (today + timedelta(days=379)).strftime('%Y-%m-%d')))
    conn.execute("INSERT INTO app_settings (key, value) VALUES ('active_serial_number', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (serial,))
    conn.commit(); conn.close()


def _set_setting(key, value):
    conn = sqlite3.connect(dental_clinic.DB_NAME)
    conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit(); conn.close()


def test_onboarding_fresh_install(local):
    b = local.get('/api/onboarding/state').get_json()
    assert b['licensed_state'] == 'unlicensed'
    assert b['cloud_linked'] is False
    assert b['needs_onboarding'] is True


def test_onboarding_licensed_unlinked_needs_onboarding(local):
    _seed_active_license()
    b = local.get('/api/onboarding/state').get_json()
    assert b['licensed_state'] == 'active'
    assert b['cloud_linked'] is False
    assert b['needs_onboarding'] is True


def test_onboarding_linked(local):
    _seed_active_license()
    _set_setting('cloud_url', 'https://cloud.example.test')
    _set_setting('cloud_clinic_token', 'tok')
    b = local.get('/api/onboarding/state').get_json()
    assert b['cloud_linked'] is True
    assert b['needs_onboarding'] is False


def test_onboarding_dismissed(local):
    _seed_active_license()
    _set_setting('cloud_link_dismissed', '1')
    b = local.get('/api/onboarding/state').get_json()
    assert b['needs_onboarding'] is False   # licensed + dismissed → done
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_onboarding_b.py -k onboarding -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement the route**

Add after `license_gate` (A3, `~:5025`):

```python
@app.route('/api/onboarding/state')
def onboarding_state():
    conn = get_db_connection()
    cursor = conn.cursor()
    gate = _license_gate_state(cursor)
    cloud_url = str(read_app_setting(cursor, 'cloud_url', '') or '').strip()
    cloud_token = str(read_app_setting(cursor, 'cloud_clinic_token', '') or '').strip()
    dismissed = str(read_app_setting(cursor, 'cloud_link_dismissed', '') or '').strip() in ('1', 'true', 'yes')
    conn.close()
    cloud_linked = bool(cloud_url and cloud_token)
    state = gate.get('state', 'unlicensed')
    licensed = state in ('active', 'grace')
    needs_onboarding = (state == 'unlicensed') or (licensed and not cloud_linked and not dismissed)
    return jsonify({
        'licensed_state': state,
        'cloud_linked': cloud_linked,
        'needs_onboarding': needs_onboarding,
    })
```

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_onboarding_b.py -k onboarding -v`
Expected: PASS. `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add dental_clinic.py tests/test_onboarding_b.py
rtk git commit -m "feat(license): B GET /api/onboarding/state drives the guided flow"
```

---

### Task 4: SPA — post-activation one-tap cloud-link panel

**Files:**
- Modify: `templates.py` (`HTML_TEMPLATE`, the A3 overlay)
- Create: `tests/test_onboarding_ui_b.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_onboarding_ui_b.py
import re
import shutil
import subprocess
import tempfile
import os
import pytest
import templates


def test_template_has_cloud_link_panel():
    html = templates.HTML_TEMPLATE
    assert 'id="license-link-cloud"' in html       # the one-tap link button
    assert 'id="license-link-skip"' in html        # "Not now"
    assert "fetch('/api/cloud/pair'" in html or 'fetch("/api/cloud/pair"' in html
    assert "fetch('/api/onboarding/state'" in html or 'fetch("/api/onboarding/state"' in html


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_template_scripts_pass_node_check():
    html = templates.HTML_TEMPLATE
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    blob = '\n;\n'.join(scripts)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
        fh.write(blob); path = fh.name
    try:
        proc = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `rtk proxy python -m pytest tests/test_onboarding_ui_b.py -v`
Expected: `test_template_has_cloud_link_panel` FAILS (markers absent).

- [ ] **Step 3: Implement**

3a. **Markup** — extend the A3 overlay card (`id="license-gate-overlay"`) with a second, initially
hidden panel:

```html
        <div id="license-link-panel" class="hidden">
          <h2>Enable secure cloud backup?</h2>
          <p>Back up this clinic to the cloud. You can do this later in Settings.</p>
          <button type="button" id="license-link-cloud" onclick="linkCloud()">Enable secure cloud backup</button>
          <button type="button" id="license-link-skip" onclick="skipCloudLink()">Not now</button>
          <div id="license-link-status" class="license-overlay__status"></div>
        </div>
```

3b. **JS** — extend the A3 `submitLicenseActivation` success path to reveal the link panel instead
of reloading immediately, and add the link/skip handlers (no literal newlines inside strings —
escaping trap):

```javascript
        // Replace the A3 success branch (window.location.reload()) with:
        //   showCloudLinkPanel();
        function showCloudLinkPanel() {
            document.querySelector('#license-gate-overlay h2').classList.add('hidden');
            document.getElementById('license-gate-token').classList.add('hidden');
            document.getElementById('license-link-panel').classList.remove('hidden');
            document.getElementById('license-gate-status').textContent = '';
        }
        async function linkCloud() {
            const status = document.getElementById('license-link-status');
            status.textContent = 'Linking...';
            try {
                const res = await fetch('/api/onboarding/state');
                const st = await res.json();
                const serial = st.serial_number || (window.__activeSerial || '');
                const res2 = await fetch('/api/cloud/pair', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ serial_number: serial })
                });
                const body = await res2.json();
                if (!res2.ok) { status.textContent = body.error || 'Could not reach the cloud — you can enable backup later in Settings.'; return; }
                window.location.reload();
            } catch (e) { status.textContent = 'Could not reach the cloud — you can enable backup later in Settings.'; }
        }
        async function skipCloudLink() {
            try {
                await fetch('/api/onboarding/dismiss-cloud-link', { method: 'POST' });
            } catch (e) { /* best-effort */ }
            window.location.reload();
        }
```

> `submitLicenseActivation` (from A3) should stash the activated serial so `linkCloud` has it
> without re-prompting: in that function's success branch, set
> `window.__activeSerial = (body.serial_number || '');` then call `showCloudLinkPanel();`.

3c. **Dismiss endpoint** — add to `dental_clinic.py` near `onboarding_state`:

```python
@app.route('/api/onboarding/dismiss-cloud-link', methods=['POST'])
def onboarding_dismiss_cloud_link():
    conn = get_db_connection()
    cursor = conn.cursor()
    write_app_setting(cursor, 'cloud_link_dismissed', '1')
    conn.commit()
    conn.close()
    return jsonify({'success': True})
```

> `/api/onboarding/*` is a write but must work pre-link; it is **not** clinical data and is reached
> only when licensed/activating, so it is unaffected by A3's view-only guard (which allowlists by
> clinical write, and an onboarding dismiss in `unlicensed`/`active` is never `view_only`). If you
> prefer belt-and-braces, add `/api/onboarding/` to A3's `_VIEW_ONLY_WRITE_ALLOW_PREFIXES`.

- [ ] **Step 4: Run to verify it passes**

Run: `rtk proxy python -m pytest tests/test_onboarding_ui_b.py tests/test_onboarding_b.py -v`
Expected: PASS (node sweep runs if `node` present). `$LASTEXITCODE` == 0.

- [ ] **Step 5: Commit**

```bash
rtk git add templates.py dental_clinic.py tests/test_onboarding_ui_b.py
rtk git commit -m "feat(license): B collapsed activation→one-tap cloud-link onboarding panel"
```

---

### Task 5: Mobile — `LicenseGateState` + `mapGateState` (pure Dart)

**Files:**
- Create: `clinic_mobile_app/lib/services/license_gate_service.dart`
- Create: `clinic_mobile_app/test/license_gate_service_test.dart`

- [ ] **Step 1: Write the failing test**

```dart
// clinic_mobile_app/test/license_gate_service_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:clinic_mobile_app/services/license_gate_service.dart';

void main() {
  group('mapGateState', () {
    test('maps active', () {
      expect(mapGateState({'state': 'active'}), isA<GateActive>());
    });
    test('maps grace with date', () {
      final s = mapGateState({'state': 'grace', 'grace_until': '2027-06-17'});
      expect(s, isA<GateGrace>());
      expect((s as GateGrace).graceUntil, '2027-06-17');
    });
    test('maps view_only', () {
      expect(mapGateState({'state': 'view_only'}), isA<GateViewOnly>());
    });
    test('maps unlicensed', () {
      expect(mapGateState({'state': 'unlicensed'}), isA<GateUnlicensed>());
    });
    test('unknown/missing → GateUnknown', () {
      expect(mapGateState({'state': 'wat'}), isA<GateUnknown>());
      expect(mapGateState({}), isA<GateUnknown>());
    });
  });
}
```

> Confirm the package name in `clinic_mobile_app/pubspec.yaml` (`name:`); replace
> `clinic_mobile_app` in the import if it differs.

- [ ] **Step 2: Run to verify it fails**

Run (from `clinic_mobile_app/`): `rtk proxy flutter test test/license_gate_service_test.dart`
Expected: FAIL to compile — `license_gate_service.dart` does not exist.

- [ ] **Step 3: Implement**

```dart
// clinic_mobile_app/lib/services/license_gate_service.dart
import 'api_client.dart';

/// The desktop is the license authority; the phone DERIVES this state over the
/// LAN from GET /api/license/gate. It never activates a license itself.
sealed class LicenseGateState {
  const LicenseGateState();
}

final class GateActive extends LicenseGateState {
  const GateActive();
}

final class GateGrace extends LicenseGateState {
  const GateGrace(this.graceUntil);
  final String graceUntil;
}

final class GateViewOnly extends LicenseGateState {
  const GateViewOnly();
}

final class GateUnlicensed extends LicenseGateState {
  const GateUnlicensed();
}

/// Desktop unreachable / unparseable — the app stays usable (offline-tolerant);
/// it only gates on an explicit view_only/unlicensed answer.
final class GateUnknown extends LicenseGateState {
  const GateUnknown();
}

/// Pure, server-free mapping so it is unit-testable without a camera or network.
LicenseGateState mapGateState(Map<String, dynamic> json) {
  switch ((json['state'] ?? '').toString()) {
    case 'active':
      return const GateActive();
    case 'grace':
      return GateGrace((json['grace_until'] ?? '').toString());
    case 'view_only':
      return const GateViewOnly();
    case 'unlicensed':
      return const GateUnlicensed();
    default:
      return const GateUnknown();
  }
}

class LicenseGateService {
  LicenseGateService([ApiClient? api]) : _api = api ?? ApiClient();
  final ApiClient _api;

  Future<LicenseGateState> fetchGate({
    required String baseUrl,
    String? deviceToken,
  }) async {
    try {
      final data = await _api.getJson(
        baseUrl: baseUrl,
        path: '/api/license/gate',
        deviceToken: deviceToken,
      );
      return mapGateState(data);
    } on Object {
      return const GateUnknown();
    }
  }
}
```

> `on Object` deliberately catches any `ApiException`/`DioException` and degrades to `GateUnknown`
> — the phone must never hard-fail on a transient LAN hiccup. (This is the one place a broad catch
> is correct: a licensing read must never crash the clinic app.)

- [ ] **Step 4: Run to verify it passes**

Run (from `clinic_mobile_app/`):
```bash
rtk proxy dart analyze lib/services/license_gate_service.dart test/license_gate_service_test.dart
rtk proxy flutter test test/license_gate_service_test.dart
```
Expected: analyze clean; all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add clinic_mobile_app/lib/services/license_gate_service.dart clinic_mobile_app/test/license_gate_service_test.dart
rtk git commit -m "feat(mobile): B LicenseGateService derives desktop license state over LAN"
```

---

### Task 6: Mobile gate screen wiring (reflect desktop state)

**Files:**
- Modify: the mobile app shell that already holds the desktop `baseUrl` + `deviceToken` (locate via `grep -rn "deviceToken" clinic_mobile_app/lib`), e.g. the home/root widget.
- Test: covered by Task 5 unit tests + `dart analyze`; widget wiring verified by `flutter analyze`.

- [ ] **Step 1: Locate the root shell + its baseUrl/deviceToken source**

Run: `rtk grep "device_token\|deviceToken\|baseUrl" clinic_mobile_app/lib`
Identify the widget that already has the paired desktop `baseUrl` and `deviceToken` after BT/LAN pairing.

- [ ] **Step 2: Wire the gate on app resume / first frame**

In that widget's `initState`/post-pair callback, call:

```dart
final gate = await LicenseGateService().fetchGate(baseUrl: baseUrl, deviceToken: deviceToken);
// then render per the spec table:
//   GateActive/GateUnknown → normal app
//   GateGrace(d)           → dismissible "Renew on the clinic desktop by $d" banner
//   GateViewOnly           → read-only mode + "Ask the clinic to renew" notice
//   GateUnlicensed         → "Activate on the desktop first" block screen
```

Use a `switch` over the sealed type (exhaustive, no default) per the Dart rules. Keep the phone
**usable** on `GateUnknown` — never block on a transient LAN failure.

- [ ] **Step 3: Static-analyse the whole app**

Run (from `clinic_mobile_app/`): `rtk proxy dart analyze`
Expected: clean (no new warnings). If the project gates CI on `dart format --set-exit-if-changed`,
run `rtk proxy dart format .` first.

- [ ] **Step 4: Run the mobile test suite (no regressions)**

Run (from `clinic_mobile_app/`): `rtk proxy flutter test`
Expected: green (existing 67 + the 5 new gate tests).

- [ ] **Step 5: Commit**

```bash
rtk git add clinic_mobile_app/lib
rtk git commit -m "feat(mobile): B gate screen reflects desktop license state, LAN-derived"
```

---

### Task 7: Full regression + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Backend regression**

```bash
rtk proxy python -m py_compile dental_clinic.py templates.py
rtk proxy python -m pytest tests/ -q
```
Expected: clean; whole backend suite (A1+A2+A3+B) green. `$LASTEXITCODE` == 0.

- [ ] **Step 2: Mobile regression**

```bash
cd clinic_mobile_app && rtk proxy dart analyze && rtk proxy flutter test
```
Expected: analyze clean, tests green.

- [ ] **Step 3: Update README test counts** (backend suites + the new Flutter test) in the existing wording style.

- [ ] **Step 4: Commit + push**

```bash
rtk git add README.md
rtk git commit -m "docs: B — record premium onboarding (backend + mobile) test suites"
rtk git push
```

---

## Self-Review

1. **Spec coverage:** baked URL (T1), one-tap link via baked URL (T2), `/api/onboarding/state` (T3),
   SPA collapsed onboarding + dismiss (T4), mobile gate state+service (T5), mobile gate screen (T6),
   regression+docs (T7). Every "In" bullet maps to a task. ✅
2. **Placeholder scan:** the only placeholder is `_BAKED_CLOUD_BASE_URL = 'https://cloud.dentacare.app'`
   with a "vendor: set the real host" comment — a real product value the vendor confirms, not a code
   gap; tests assert *behaviour relative to the constant*, not its literal value.
3. **Type/name consistency:** `_license_cloud_url`/`_BAKED_CLOUD_BASE_URL` consistent across T1/T2;
   `/api/onboarding/state` field names (`licensed_state`, `cloud_linked`, `needs_onboarding`) match
   the SPA reads; the sealed `LicenseGateState` variants used in T5 match the T6 switch and the spec
   table; `mapGateState`/`fetchGate` signatures match their call sites and tests.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-licensing-b-onboarding.md`. Two options:

1. **Subagent-Driven (recommended)** — fresh subagent per task; run them **one at a time** (the earlier 5-way parallel fan-out hit the account session limit). Backend and mobile tasks can be split across two sequential subagents.
2. **Inline Execution** — implement T1–T7 in-session with checkpoints.

**Which approach?** (Or continue to the next plan — C — since you asked for all five.)
