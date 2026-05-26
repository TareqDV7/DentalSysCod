# Standalone Windows .exe Migration — Design

**Date:** 2026-05-26
**Author:** Brainstormed with operator (TareqDV7)
**Status:** Approved — ready for implementation planning
**Estimated effort:** ~4 days of implementation, 4 milestones

---

## Goal

Convert DentaCare from "Flask web app the customer accesses through a browser" to a real standalone Windows desktop application: an installer drops a windowed program onto the customer's machine, the program runs as a background Windows service, and the customer sees a normal desktop window with the existing UI inside — no browser, no URL bar, no exposed port number.

The migration is foundational for a follow-up spec that simplifies the Bluetooth setup UX (Approach C: silent install-time COM port provisioning). It is **not** a UI redesign — every Flask route, every HTML template, every test in `dental_clinic.py` stays as-is.

## Non-goals

- BT setup UX redesign — separate spec, comes next after this one ships
- Installer-time serial / activation enforcement — deferred to its own future spec
- Code signing / SmartScreen suppression — leave the hook in the build, ship unsigned for v1, revisit at ~50 paying customers
- Auto-update mechanism — v1 customers re-run the installer
- macOS / Linux native packaging — cloud node (Docker) and Linux dev (`python3 dental_clinic.py`) still work unchanged

## Architecture

Three runtime components, plus an installer that wires them together.

### Component 1 — `DentaCareService.exe` (headless Flask)

The existing `dental_clinic.py` packaged as a single binary, launched headlessly. Same Flask routes, same SQL schema, same sync threads, same tests. The only Python-side change is that it knows how to find its data directory in three modes:

| Run mode | Data directory resolution |
|---|---|
| From source (`python dental_clinic.py`) — `sys.frozen` is False | Current working directory (today's behavior) |
| Packaged exe (`sys.frozen` is True), no `CLINIC_DATA_DIR` set | `C:\ProgramData\DentaCare\` |
| Any mode, `CLINIC_DATA_DIR` env var set | The value of `CLINIC_DATA_DIR` (today's Docker behavior preserved) |

Wrapped as a Windows service by **NSSM** (Non-Sucking Service Manager — 300 KB MIT-licensed binary), service name `DentaCare`, account `LocalSystem`, working directory `C:\ProgramData\DentaCare\`. Auto-starts at Windows boot. NSSM restarts the service on crash with exponential backoff (1s → 5s → 30s caps, gives up after 3 failures in 60s). All stdout/stderr captured to `C:\ProgramData\DentaCare\logs\service.{stdout,stderr}.log`, rotated at 10 MB, last 5 kept.

Flask binds `127.0.0.1:5000` (loopback only) for the window app. LAN access for mobile sync goes through the existing `CLINIC_HOST=0.0.0.0` configuration.

### Component 2 — `DentaCare.exe` (window launcher)

New thin Python entry point, ~80 lines, file: `dentacare_window.py`. Uses **pywebview** (Edge WebView2 engine on Windows 10/11) to render the existing UI in a windowed app.

Behavior:

- **Launch:** check the service is reachable at `http://127.0.0.1:5000/healthz`. If 503 or connection refused, retry with backoff for up to 10 seconds (handles "service still starting" right after boot). On success, open a pywebview window pointed at `http://127.0.0.1:5000`. Window has standard Windows chrome (title bar, min/max/close), DentaCare icon, opens at 1280×800 by default, remembers size/position across launches in `%LOCALAPPDATA%\DentaCare\window-state.json`.
- **Service unreachable after retry budget:** show a built-in offline page (`offline.html` bundled with the exe): *"DentaCare engine is starting… (or stopped)"* with a **Restart engine** button that runs `sc start DentaCare` (UAC elevation if needed). Polls `/healthz` every 2 s and auto-loads the real UI when the service responds.
- **Single-instance enforcement** via a named Windows mutex (`DentaCare-Window-Singleton`). Re-launching the Start Menu icon while the window already exists posts a focus message to the existing instance instead of opening a second window.
- **X button:** hides the window. Once per session, shows a notification balloon: *"DentaCare is still running. Right-click the tray icon to fully quit."*
- **Tray icon:** DentaCare logo in the Windows notification area. Right-click menu: *Open*, *Restart engine*, *Open log folder*, *Quit completely*. *Quit completely* exits the window app; the service keeps running so mobile sync stays alive.

### Component 3 — `DentaCare-Setup.exe` (Inno Setup installer)

Standard Inno Setup installer. Source script `installer\DentaCare.iss`, ~150 lines. Behavior:

1. Welcome → License → Install location (default `C:\Program Files\DentaCare\`) → Components → Ready → Install
2. Component checkboxes: "Desktop shortcut" (default off), "Launch DentaCare window at logon" (default on)
3. One UAC prompt at the start of "Install" — every subsequent step runs elevated
4. Copies files to `C:\Program Files\DentaCare\`: `DentaCare.exe`, `DentaCareService.exe`, `nssm.exe`, `DentaCare.PNG`, `installer\provision_bt.ps1`
5. Creates `C:\ProgramData\DentaCare\{uploads,backups,logs}\`; runs `icacls` to grant `LocalSystem` write access
6. **Database migration**: if a `dental_clinic.db` is found in the legacy portable locations (Desktop, the path from a `start.bat` shortcut, or wherever the user is currently running from), copy (not move) it to `C:\ProgramData\DentaCare\dental_clinic.db` after a confirmation dialog. Original left as a safety backup. Pairs over the existing `paired_devices` table, license tokens, cloud sync state, and all clinic data.
7. Registers NSSM service: `nssm install DentaCare "C:\Program Files\DentaCare\DentaCareService.exe"`, account `LocalSystem`, working dir `C:\ProgramData\DentaCare\`, auto-start, stdout/stderr to log files
8. **BT COM port provisioning**: runs `powershell -ExecutionPolicy Bypass -File provision_bt.ps1`. Script is idempotent — skips if any Incoming SPP COM port already exists, otherwise adds one via the documented Windows BT registry path
9. Creates Start Menu group "DentaCare" → *DentaCare* (window app) + *Uninstall*
10. Adds HKCU `Run` registry entry pointing at `DentaCare.exe` (if the "launch at logon" checkbox is ticked)
11. **WebView2 bootstrap**: if `HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` is missing (no WebView2 runtime), runs the bundled Evergreen Bootstrapper (~3 MB) to install it silently
12. "Finish" step launches `DentaCare.exe` — by then the service is already running

**Upgrade flow:** Inno Setup detects existing install via its own registry entries. Stops the service via `sc stop DentaCare` (30 s graceful timeout), overwrites the binaries in `Program Files`, restarts the service. **Never touches `ProgramData\DentaCare\`.** SQLite schema migrations happen on next service start via the existing `init_database()` idempotent call.

**Uninstall flow:** Stops + removes the service. Removes `Program Files\DentaCare\`. **Asks before touching `ProgramData\DentaCare\`** — defaults to KEEP (the customer's clinic data is sacred). Removes HKCU Run registry entry. Does NOT remove the Incoming SPP COM port (other apps may use it).

## File layout after install

```
C:\Program Files\DentaCare\               (read-only, requires admin to modify)
├── DentaCare.exe                         (window launcher — what Start Menu points to)
├── DentaCareService.exe                  (headless Flask, run by NSSM)
├── nssm.exe                              (service shim, bundled)
├── DentaCare.PNG                         (icon)
├── unins000.exe                          (Inno Setup uninstaller)
└── installer\provision_bt.ps1            (kept for repair / uninstall)

C:\ProgramData\DentaCare\                 (writable to the service account)
├── dental_clinic.db                      (SQLite DB lives here)
├── uploads\                              (medical images)
├── backups\                              (auto-generated backups)
└── logs\
    ├── service.stdout.log                (NSSM-captured stdout)
    └── service.stderr.log                (NSSM-captured stderr)

%LOCALAPPDATA%\DentaCare\                 (per-user, written by the window app)
└── window-state.json                     (last size / position)

HKLM\System\CurrentControlSet\Services\DentaCare    (NSSM service registration)
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\DentaCare    (auto-launch at logon, optional)
```

## What does NOT change

- `dental_clinic.py` Flask routes, templates, SQL schema, sync logic — none of it
- `serial_generator.py` and the entire `/api/license/*` activation flow — preserved as-is; the `paired_devices` table and license tokens move with the database
- Cloud node (`CLINIC_CLOUD_MODE=1`) — runs in Docker, never sees the installer or window app
- The Flutter mobile app — completely untouched; still hits `http://<clinic-pc>:5000/api/...` exactly as it does today
- The 170 existing tests — all keep passing; new tests add to the suite
- The browser dev workflow (`python dental_clinic.py` opens in the system default browser with Werkzeug auto-reloader) — preserved unchanged

## Testing strategy

### Automated (pytest, runs in CI)

| Area | Test approach |
|---|---|
| Data-dir resolution | Unit test `CLINIC_DATA_DIR` + `sys.frozen` branching. Asserts source mode uses CWD; `CLINIC_DATA_DIR` overrides everything; frozen + no env picks `ProgramData\DentaCare\`. |
| Service mode startup | Subprocess test: launches `dental_clinic.py` with `CLINIC_DATA_DIR=<tmp>`, polls `/healthz` until 200, asserts DB created in the right place. |
| Window app health polling | Unit test the retry-with-backoff logic: mock `/healthz` responses (`Connection refused` → `503` → `200`), verify the timeout budget and that success fires once. |
| Single-instance mutex | Spawn two instances of the window app in sequence via subprocess; assert the second exits cleanly and posts a focus message to the first. |
| Existing 170 tests | Unchanged. Must keep passing after every milestone. |

CI matrix stays Python 3.10, 3.11, 3.12 on Ubuntu. New tests use stdlib `subprocess` + `socket`, no Windows-only dependencies.

### Manual smoke-test on Windows VM (gated before release)

Run on a clean Windows 11 VM and a clean Windows 10 22H2 VM:

| Test | Pass criteria |
|---|---|
| Clean install (no prior DentaCare) | UAC once → install completes → service running → window opens to sign-in page → mobile can sync over LAN |
| Clean install on Win 10 22H2 | Above, plus WebView2 bootstrapper runs (verify in install log) |
| Upgrade install (v1.0 → v1.1) | DB preserved, paired devices preserved, no UAC mid-upgrade beyond the initial one |
| Uninstall keeping data | `ProgramData\DentaCare\` survives; re-install re-uses it (paired devices intact) |
| Uninstall removing data | Both folders gone; clean state |
| BT provisioning, no existing port | `provision_bt.ps1` adds one; verify with `Get-PnpDevice` and the COM Ports dialog |
| BT provisioning, port already exists (operator's machine) | Script detects, no-ops, exits 0 |
| Service crash recovery | Force-kill `DentaCareService.exe` via Task Manager → NSSM restarts within 5 s |
| Window app while service is down | `sc stop DentaCare` → offline page shown; `sc start DentaCare` → window auto-reloads UI |
| Single-instance | Click Start Menu icon twice while window is open → second click brings existing window to front, doesn't open another |
| Close → tray → quit | X button hides → tray icon visible → *Quit completely* exits app but service keeps running → re-open from Start Menu works |
| Auto-launch on reboot | Tick "Launch at logon" during install → reboot → window app opens after logon |
| SmartScreen on unsigned build | First run shows "Windows protected your PC" → "More info" → "Run anyway" → second run skips the warning |
| Defender / Controlled Folder Access | No `0xc0000022` errors launching from Start Menu (Program Files is implicitly trusted; verify on operator's machine since CFA has affected the project before) |

## Implementation milestones

Implementation splits into four independently shippable milestones. Each ends with a PR that keeps all 170 existing tests + new ones green. Pause-and-ship is possible between any of them.

| # | Milestone | Shippable outcome | Effort |
|---|---|---|---|
| **A** | Service-mode refactor + data-dir resolution | `dental_clinic.py` handles `CLINIC_DATA_DIR` cleanly, `sys.frozen` detection branches correctly, headless mode skips the browser auto-open. Runnable manually from a terminal as a "service simulation". Existing browser dev mode untouched. | ~1 day |
| **B** | pywebview window app + single-instance + healthz polling | `dentacare_window.py` works as a standalone script today (`python dentacare_window.py` against a running service). Tray icon + close-to-hide + offline page all functional. Not yet a packaged exe. | ~1 day |
| **C** | PyInstaller two-binary spec + NSSM service registration | `rebuild.bat` produces `DentaCare.exe` + `DentaCareService.exe`. A standalone `register-service.bat` registers / unregisters via NSSM. Manual install path works end-to-end — without the Inno Setup wrapper. | ~1 day |
| **D** | Inno Setup installer + BT provisioning + first-launch UX | `DentaCare-Setup.exe` produced. All edge cases from the smoke-test table pass. **This is the customer-shippable artifact.** | ~1 day |

## Operational details

### Code signing (deferred)

Unsigned binaries trigger Windows SmartScreen on first launch: *"Windows protected your PC… don't run this app."* Customer clicks *More info → Run anyway*. Embarrassing but harmless. Code-signed binaries (OV cert ~$200/year, EV cert ~$300-400/year) suppress the warning. Spec leaves the signing step in the build script but commented out — uncomment once the operator decides to invest.

### Logging & support workflow

When a customer reports "DentaCare isn't working":

1. Tell them to send `C:\ProgramData\DentaCare\logs\service.stderr.log` (+ `.stdout.log`)
2. Logs include request lines, BT/cloud-sync outcomes, stack traces if any
3. Tray icon right-click → *Open log folder* opens Explorer to the directory — one step for the customer

This is the operational hand-off improvement over today, where the customer can't see Werkzeug's console output once the terminal is closed.

### What the operator can do unaided

- **Read logs:** `C:\ProgramData\DentaCare\logs\service.stderr.log`
- **Restart engine:** `services.msc` or tray right-click → *Restart engine*
- **Move to a new PC:** copy `C:\ProgramData\DentaCare\` to the new machine after installing
- **Back up everything:** `C:\ProgramData\DentaCare\` is the entire clinic state

## Risks & unknowns

| Risk | Mitigation |
|---|---|
| WebView2 missing on older Windows 10 builds | Installer bundles Microsoft's Evergreen Bootstrapper (~3 MB); auto-installs WebView2 if absent. Verified in Milestone D smoke test on Win 10 22H2. |
| NSSM + `LocalSystem` writing to `ProgramData` blocked by ACLs | Installer runs `icacls C:\ProgramData\DentaCare /grant SYSTEM:(OI)(CI)F`. Verified in Milestone D smoke test. |
| `provision_bt.ps1` idempotency on machines with existing Incoming SPP ports | Script reads the COM Ports registry, skips if any incoming SPP port exists. Tested on operator's machine (has Buds-labeled incoming port) and on a clean VM. |
| Customer loses data on upgrade | Database migration is COPY not MOVE; original stays as safety backup. Confirmation dialog before any copy. ProgramData never touched on upgrade. |
| Defender / Controlled Folder Access (project_windows_cfa.md) | `Program Files` is implicitly trusted by CFA; should be a non-issue. Verified explicitly in Milestone D smoke test on the operator's machine since CFA has affected this project before. |
| pywebview + WebView2 quirks on multi-monitor / DPI scaling | Window state persistence (size/position) clamps to current monitor bounds at restore to handle disconnected secondary displays. |
| First customer who reports an issue from a SmartScreen-rejected install | One-page customer-facing PDF explaining the *More info → Run anyway* dance, included in customer onboarding. |

## Follow-up specs unlocked by this one

1. **BT UX redesign (Approach C — silent setup, toggle-only card)** — Once Milestone D ships the install-time COM port provisioning, the BT card simplifies to a toggle + status line. Mobile gets a one-time wizard for the irreducible Android permissions + Windows pairing step. Estimated ~1 day after this lands.
2. **Installer-time serial enforcement** — Add a license-key screen to the installer; validate via HMAC signing key; refuse install on blank/invalid. ~½ day. Deferred per operator decision in this brainstorming session.
3. **Auto-update mechanism** — Velopack or custom updater; revisit after field experience.
4. **Code signing investment** — OV cert + signing in build script; revisit at ~50 paying customers.
