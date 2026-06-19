# Code-Signing the DentaCare Windows Build

Unsigned binaries trigger SmartScreen's **"Windows protected your PC — unknown publisher"**
warning, which is a serious conversion-killer for a paid product that solo clinics install
themselves. This doc covers choosing a certificate and signing the build.

> **Status:** the build is *wired* for signing (gated, opt-in) but **no certificate is
> purchased yet**. Until then, builds are unsigned and work normally. Buying the cert is the
> one manual prerequisite.

---

## 1. Choosing a certificate

Since June 2023, the CA/Browser Forum requires code-signing private keys to live on certified
hardware (a USB token) or a cloud HSM — you can no longer get a plain downloadable `.pfx`.
**Avoid physical USB tokens** (awkward on a build machine, can't automate). Prefer **cloud
signing**, where `signtool` talks to a hosted key.

Two trust levels:
- **OV (Organization Validation):** cheaper, but SmartScreen still warns until the certificate
  slowly *earns reputation* across many installs — painful for a brand-new, low-volume product.
- **EV (Extended Validation):** **instant** SmartScreen trust, zero "unknown publisher" from the
  first install. Worth it for a product you're actively selling.

### Recommended options (verify current pricing/eligibility at purchase — this list may age)

| Option | Trust | ~Cost | Notes |
|---|---|---|---|
| **Azure Trusted Signing** | EV-equivalent (Microsoft-rooted) | **~$10/mo** | Cheapest + cleanest `signtool` integration (cloud, no token). Requires identity validation; **individual** accounts historically need a 3-year verifiable history, **organization** needs business docs. Try this **first** if eligible. |
| **SSL.com eSigner (EV)** | EV | ~$250–500/yr | Cloud signing (no token), explicitly serves MENA/Gulf customers, instant SmartScreen trust. Solid fallback. |
| **Sectigo EV via reseller** (Codegic, SignMyCode, Certera…) | EV | ~$250–400/yr | Resellers accept international/MENA customers; pick one offering **cloud** signing, not a shipped token. |

**Recommendation for the solo-dentist / MENA beachhead:** try **Azure Trusted Signing** first
(cheapest, cleanest, Microsoft-trusted). If identity validation doesn't fit, get an **EV cert
with cloud signing from SSL.com eSigner** (or a Sectigo EV reseller with cloud signing). The
certificate **subject name** is what clinics see as the publisher — register it under the
business/clinic name you want shown.

---

## 2. Install the signing tool

`signtool.exe` ships with the **Windows SDK**. You do **not** need full Visual Studio — install
only the **"Signing Tools for Desktop Apps"** component of the Windows 10/11 SDK. After install
it lives under `C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe`
(`rebuild.bat` auto-discovers it there).

A cloud-signing provider (Azure Trusted Signing, eSigner, etc.) also gives you a **dlib** and a
small **metadata** file that `signtool` uses to reach your hosted key — follow their quick-start.

---

## 3. Build a signed release

Signing is **opt-in** via two environment variables. `DENTACARE_SIGNTOOL_ARGS` is everything you
pass to `signtool sign` *except the file* (the build appends the file).

### a) Sign the two binaries (`rebuild.bat`)

```bat
set DENTACARE_SIGN=1
REM Example for a hardware-token / cert-store EV cert:
set DENTACARE_SIGNTOOL_ARGS=/fd sha256 /a /tr http://timestamp.sectigo.com /td sha256
rebuild.bat
```

For **cloud** signing (e.g. Azure Trusted Signing) the args instead point at the dlib + metadata:

```bat
set DENTACARE_SIGN=1
set DENTACARE_SIGNTOOL_ARGS=/v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 /dlib "C:\path\Azure.CodeSigning.Dlib.dll" /dmdf "C:\path\metadata.json"
rebuild.bat
```

`rebuild.bat` signs `dist\DentaCare.exe` + `dist\DentaCareService.exe`, runs
`signtool verify /pa`, then stages the **signed** binaries for the installer. Leaving
`DENTACARE_SIGN` unset skips signing entirely (unsigned dev build, unchanged behavior).

### b) Sign the installer (`DentaCare.iss`)

```bat
ISCC /DSIGN "/Ssigntool=signtool.exe sign /fd sha256 /a /tr http://timestamp.sectigo.com /td sha256 $f" installer\DentaCare.iss
```

`/DSIGN` activates the `SignTool=signtool` + `SignedUninstaller=yes` block; the `/Ssigntool=...`
switch defines the named command Inno runs (`$f` = the file). Without `/DSIGN`, the installer
compiles **unsigned** (today's default). Use the same arg style (token vs cloud dlib) as 3a.

> Full path to ISCC on this machine: `C:\Users\MSI\AppData\Local\Programs\Inno Setup 6\ISCC.exe`.

---

## 4. Verify

```bat
signtool verify /pa /v dist\DentaCare.exe
signtool verify /pa /v "installer\Output\DentaCare-Setup.exe"
```

Then do a real install on a clean Windows VM and confirm **no SmartScreen "unknown publisher"
prompt** appears (EV) or that the publisher name shows correctly (OV). EV should be clean
immediately; OV may still warn until reputation builds.

---

## 5. Order of operations at release time

1. Buy + provision the cert (one-time).
2. `set DENTACARE_SIGN=1` + `DENTACARE_SIGNTOOL_ARGS=...`, run `rebuild.bat` → signed binaries.
3. `ISCC /DSIGN "/Ssigntool=..." installer\DentaCare.iss` → signed `DentaCare-Setup.exe`.
4. Verify (step 4), smoke-install on a clean VM, then distribute.
