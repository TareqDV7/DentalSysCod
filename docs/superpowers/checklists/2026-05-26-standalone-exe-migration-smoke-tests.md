# Standalone-exe migration — manual smoke test checklist

**Branch:** `migration/standalone-exe`
**Spec:** `docs/superpowers/specs/2026-05-26-standalone-exe-migration-design.md`
**Plan:** `docs/superpowers/plans/2026-05-26-standalone-exe-migration.md`

Run through this in order on a real Windows machine. Each item has its exact command, what to look for, and what to do if it fails. Tick each box as you go.

## Pre-flight

- [ ] You're on the right branch: `rtk git status` shows `On branch migration/standalone-exe` with a clean tree.
- [ ] Existing automated suite passes: `rtk python -m pytest tests/ -v` reports `187 passed`.
- [ ] Python deps installed: `rtk python -c "import webview, pystray, PIL"` prints `ok` (or no error).

---

## Section 1 — Window app behaves like a desktop app (Phase B)

These tests run against the **source** code; no packaging needed yet.

### 1.1 Window opens to the UI

- [ ] **Terminal 1:** `rtk python dental_clinic.py`
  - Wait until you see `✅ System ready!`. A browser tab may open to `http://localhost:5000` — that's the dev-mode auto-open, expected.
- [ ] **Terminal 2 (separate window):** `rtk python dentacare_window.py`
  - **Expected:** A native Windows window opens with title bar "DentaCare", min/max/close buttons, and the existing DentaCare sign-in page rendered inside.
  - **NOT expected:** A browser tab, a URL bar, or the text "localhost:5000" visible anywhere in the window.
  - **If it fails:** Check that Edge WebView2 is installed (Windows 11 has it; Windows 10 may not). Open `https://developer.microsoft.com/microsoft-edge/webview2/` to verify and install the Evergreen Standalone if missing.

### 1.2 Offline page when the service is down

- [ ] Stop Terminal 1's `dental_clinic.py` (Ctrl-C).
- [ ] Close the DentaCare window from Section 1.1.
- [ ] **Terminal 2:** `rtk python dentacare_window.py` (without the service running)
  - **Expected:** Window opens to a blue gradient "DentaCare is starting…" page with a spinner and a "Restart engine" button.
- [ ] **Terminal 1:** Restart the service — `rtk python dental_clinic.py`. Wait for `✅ System ready!`.
  - **Expected:** Within ~2 seconds the offline window auto-loads the real DentaCare UI (no need to click anything).
  - **If it fails:** Check the in-page JS poll — open the browser DevTools via the pywebview window menu (F12 may work; if not, this is acceptable to skip).

### 1.3 Single-instance enforcement

- [ ] Keep the service running. The DentaCare window from 1.2 is open.
- [ ] **Terminal 3 (new window):** `rtk python dentacare_window.py`
  - **Expected:** Terminal 3 exits immediately (no second window opens). The existing DentaCare window (the one already open) comes to the front and gets focus.
  - **If it fails:** The named mutex may not be working. Verify on Windows 11 (older Windows 10 builds sometimes have stricter mutex behavior in sandboxed shells).

### 1.4 Tray icon + close-to-hide

- [ ] In the DentaCare window from 1.2, click the **X** button.
  - **Expected:** Window disappears. A DentaCare tray icon appears in the Windows notification area (bottom-right of the taskbar).
- [ ] **Left-click** the tray icon.
  - **Expected:** Window re-appears (the default action on the tray icon is *Open*).
- [ ] **Right-click** the tray icon.
  - **Expected:** Menu shows *Open*, *Restart engine*, *Open log folder*, *Quit completely*.
- [ ] Click *Open log folder*.
  - **Expected:** Windows Explorer opens to `<repo-root>\logs\` (in dev mode this is created on demand under your repo; in production it'd be `C:\ProgramData\DentaCare\logs\`).
- [ ] Click *Quit completely*.
  - **Expected:** Tray icon disappears, window destroyed, the launcher process exits. The `dental_clinic.py` service in Terminal 1 keeps running (verify with `rtk curl http://127.0.0.1:5000/healthz` — should still respond).

---

## Section 2 — Building both binaries (Phase C)

### 2.1 Two-binary PyInstaller build

- [ ] **From the repo root, any terminal:** `rebuild.bat`
  - **Expected:** Runs for ~3-5 minutes. Output ends with:
    ```
    Build complete:
      dist\DentaCare.exe          (window launcher)
      dist\DentaCareService.exe   (headless service)
      dist\staging\               (installer payload for Inno Setup)
    ```
  - **Verify:** `rtk ls dist/` shows both `.exe`s. `rtk ls dist/staging/` shows DentaCare.exe, DentaCareService.exe, DentaCare.PNG, nssm.exe, provision_bt.ps1, MicrosoftEdgeWebview2Setup.exe.
  - **If it fails:** Read the PyInstaller output. Common cause: missing hidden import — add it to the `COMMON_HIDDEN` list in `DentaCare.spec` and re-run.

### 2.2 Standalone service registration via NSSM

> **Requires an admin command prompt.** Open *cmd.exe* via right-click → *Run as administrator*.

- [ ] **From the admin cmd, from the repo root:** `register-service.bat`
  - **Expected:** Output shows directory creation, NSSM install, service start. Ends with `Done. Verify at: http://127.0.0.1:5000/healthz`.
- [ ] **Verify the service is running:** Open `services.msc` (Start → type "Services"). Find `DentaCare` → Status should be `Running`, Startup type `Automatic`.
- [ ] **Verify the API responds:** In any browser, visit `http://127.0.0.1:5000/healthz`.
  - **Expected:** JSON like `{"db_writable": true, "mode": "local", "status": "ok", ...}`.
- [ ] **Verify the window connects to the running service:** Double-click `dist\DentaCare.exe`.
  - **Expected:** Window opens to the DentaCare sign-in page (`admin` / `admin` on first run).
- [ ] **Verify data location:** `rtk ls "%PROGRAMDATA%\DentaCare\"` shows `uploads`, `backups`, `logs`, and (after first launch) `dental_clinic.db`.

### 2.3 Clean teardown

- [ ] **From the admin cmd:** `unregister-service.bat`
  - **Expected:** Output `Done. %PROGRAMDATA%\DentaCare left in place.`
  - **Verify:** `services.msc` no longer shows DentaCare.
  - **Verify:** `rtk ls "%PROGRAMDATA%\DentaCare\"` still has the data folder — uninstall must never touch clinic data without consent.
- [ ] **Optional cleanup before Section 3:** Delete `C:\ProgramData\DentaCare\` manually so Section 3's "clean install" really is clean. Skip this step if you want to test the upgrade path with existing data.

---

## Section 3 — Customer-facing installer (Phase D)

> **Requires Inno Setup 6 installed.** Download from https://jrsoftware.org/isdl.php if you don't have it.

### 3.1 Compile the installer

- [ ] **From any cmd (not necessarily admin):**
  ```
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DentaCare.iss
  ```
- [ ] **Verify:** `rtk ls installer/Output/` shows `DentaCare-Setup.exe` (~50-60 MB).

### 3.2 Clean install on a fresh Windows VM

> **Recommended:** Use a Windows 11 VM snapshot you can roll back. If testing on your dev machine, first uninstall any prior DentaCare and back up `%PROGRAMDATA%\DentaCare\`.

- [ ] Copy `DentaCare-Setup.exe` to the VM.
- [ ] **Double-click `DentaCare-Setup.exe`.**
  - **SmartScreen on first run:** "Windows protected your PC" — click *More info* → *Run anyway*. (Expected for unsigned builds. Customer onboarding doc should explain this.)
- [ ] Wizard flow:
  - [ ] Welcome → Next
  - [ ] License → Accept → Next
  - [ ] Install Location → leave default (`C:\Program Files\DentaCare`) → Next
  - [ ] Components — tick "Launch DentaCare window at logon" → Next
  - [ ] Ready to Install → Install
  - [ ] UAC prompt → Yes
- [ ] Watch installer progress messages:
  - "Installing Microsoft Edge WebView2 runtime..." (only if WebView2 missing — on Win 11 this is usually skipped)
  - "Configuring Bluetooth sync..." (PowerShell runs hidden)
  - Service registration steps (hidden)
- [ ] **Finish step:** Tick "Launch DentaCare" → Finish.
  - **Expected:** DentaCare window opens to the sign-in page.

### 3.3 Post-install verification

- [ ] `services.msc` — `DentaCare` Running, Automatic startup.
- [ ] `C:\Program Files\DentaCare\` contains: `DentaCare.exe`, `DentaCareService.exe`, `nssm.exe`, `DentaCare.PNG`, `installer\provision_bt.ps1`, `unins000.exe`.
- [ ] `C:\ProgramData\DentaCare\` contains: `uploads\`, `backups\`, `logs\`, `dental_clinic.db`.
- [ ] `C:\ProgramData\DentaCare\logs\service.stdout.log` is non-empty (proves NSSM is capturing the service's stdout).
- [ ] Start Menu has a "DentaCare" group with: *DentaCare* (the launcher), *Uninstall DentaCare*.
- [ ] **Reboot the VM.** After Windows logs in:
  - **Expected:** Within ~10 seconds, the DentaCare window opens automatically (because the autostart task was ticked).

### 3.4 Legacy DB migration

> Best tested on a separate VM run, before installing. Skip if you already installed in 3.2.

- [ ] On the VM, **before** installing: drop any file named `dental_clinic.db` on the user's Desktop (a small empty file is fine for the prompt).
- [ ] Run `DentaCare-Setup.exe`.
- [ ] **Expected:** During install (after files copied), a dialog appears:
  > Existing DentaCare database found:
  > C:\Users\<user>\Desktop\dental_clinic.db
  > Copy it to the new location so your patient data carries over?
- [ ] Click **Yes**.
- [ ] After install completes: `C:\ProgramData\DentaCare\dental_clinic.db` exists. The original on Desktop is **still there** (migration is copy, not move).

### 3.5 Upgrade install (v1.0 → v1.1)

> Skip if you don't want to test this; not blocking for first release.

- [ ] Edit `installer\DentaCare.iss`: change `MyAppVersion` from `1.1.0` to `1.1.0+test`.
- [ ] Recompile: `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DentaCare.iss`.
- [ ] Copy the new `DentaCare-Setup.exe` to the VM (where DentaCare is already installed from 3.2).
- [ ] Run the new installer.
- [ ] **Expected:** Detects existing install, single UAC prompt, service stops + reinstalls + restarts, DB and paired devices preserved.

### 3.6 Uninstall — keep data

- [ ] On the VM, Control Panel → Apps → DentaCare → Uninstall.
- [ ] **Expected at the end:** dialog
  > Remove DentaCare clinic data?
  > Click NO to keep the data (recommended).
- [ ] Click **No**.
- [ ] **Verify:**
  - `C:\Program Files\DentaCare\` is gone.
  - `C:\ProgramData\DentaCare\` is **still there** with all clinic data intact.
  - `services.msc` no longer shows DentaCare.
- [ ] **Re-install** from the same installer.
- [ ] **Expected:** Install completes, DentaCare window opens, sign-in screen uses your **existing** admin credentials (the DB was preserved).

### 3.7 Uninstall — delete data

- [ ] Uninstall again.
- [ ] At the data prompt, click **Yes**.
- [ ] **Verify:**
  - Both `C:\Program Files\DentaCare\` and `C:\ProgramData\DentaCare\` are gone.
  - Re-installing from the same installer behaves like a first install (`admin` / `admin` sign-in, no patient data).

---

## Section 4 — Edge cases (recommended but optional)

### 4.1 WebView2 missing path

> Only relevant if you have a Windows 10 VM without WebView2. Newer Win 10 builds ship with it; only old un-updated systems lack it.

- [ ] On a Win 10 VM that doesn't have WebView2 (verify by running `reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients" /s` — if no `{F30172...}` entry exists, WebView2 is missing).
- [ ] Run `DentaCare-Setup.exe`.
- [ ] **Expected:** "Installing Microsoft Edge WebView2 runtime..." message appears for ~30 seconds during install. Install completes normally. Window opens after install.

### 4.2 Service crash recovery

- [ ] On a VM with DentaCare installed and running, open Task Manager.
- [ ] Find `DentaCareService.exe`, right-click → End task.
- [ ] **Expected within ~5 seconds:** NSSM restarts it automatically. `services.msc` shows DentaCare back to Running. `http://127.0.0.1:5000/healthz` responds.

### 4.3 BT provisioning on a machine without an Incoming SPP port

> If your test machine doesn't already have an Incoming SPP port — the dev machine you've been using DID at one point, but the registry showed it empty during D2 testing.

- [ ] During install, watch for the Bluetooth COM Ports dialog opening (the `provision_bt.ps1` fallback when no incoming SPP port is found).
- [ ] Customer would then click *Add → Incoming → OK* manually. For automated testing, you can skip clicking — the rest of the install continues regardless.
- [ ] **Verify after install:** Bluetooth Settings → More Bluetooth Settings → COM Ports tab shows at least one **Incoming** row.

### 4.4 Defender / Controlled Folder Access

- [ ] On the dev machine (where CFA blocked `dental_clinic.py` from Desktop in the past), launch DentaCare from the Start Menu.
- [ ] **Expected:** No `0xc0000022` error. Window opens normally. (Reason: `C:\Program Files\DentaCare\` is implicitly trusted by CFA, unlike the user Desktop.)

---

## When everything passes

- [ ] All boxes above ticked.
- [ ] All 187 automated tests still pass (re-run `rtk python -m pytest tests/`).
- [ ] No surprises in `git status` or `git diff` on the branch.

**Merge:**

```
rtk git checkout main
rtk git merge migration/standalone-exe
rtk git push
```

Or use `superpowers:finishing-a-development-branch` for a guided checkout that opens a PR instead of fast-forward merging.

**Tag the release:**

```
rtk git tag -a v1.1.0 -m "Standalone Windows installer + BT timing fix"
rtk git push origin v1.1.0
```

**Ship:** upload `installer\Output\DentaCare-Setup.exe` to your distribution channel.

---

## If something fails

- Capture exact error text + screenshot.
- Note which checkbox failed and what you tried.
- Logs to grab: `C:\ProgramData\DentaCare\logs\service.{stdout,stderr}.log`, Inno Setup install log (location displayed at end of install if it fails), Event Viewer (Windows Logs → System) for service failures.
- Send the failure report back to Claude with the spec/plan filenames and which section failed. Don't merge the branch until the failure is understood.
