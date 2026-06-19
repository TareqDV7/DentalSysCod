# DentaCare — Launch-Readiness To-Do (scale-up roadmap)

> Gap analysis to take DentaCare from a strong single-clinic product to something
> launchable at large scale. Grounded in the current codebase
> (`dental_clinic.py` ~6.8k LOC, `templates.py` ~7.7k LOC, SQLite-per-tenant cloud,
> manual serial minting, Android-only mobile, unsigned installer).
>
> Priority tags: 🔴 blocker · 🟠 high · 🟡 medium · 🟢 nice-to-have
> Effort: S (<1 day) · M (days) · L (1–2 wks) · XL (weeks)

---

## GATE 0 — Decide the strategic fork (do this first, it reorders everything)

- [ ] **Decide: self-hosted product vs. cloud SaaS.** This determines whether SQLite stays or Postgres is mandatory, and how much compliance/ops work is in scope. _(Recommended: launch self-hosted-first, let cloud demand pull the heavy infra.)_ 🔴 · S
- [ ] **Decide pricing model.** One-time $3K? $X/yr subscription? Per-seat / per-chair? The licensing code already supports expiry/grace/revoke — pick the commercial model. 🔴 · S
- [ ] **Decide target segment + region.** Solo dentist vs. multi-chair clinic vs. chain; which country/language/regulatory regime. This scopes compliance and the funnel. 🔴 · S

---

## PHASE 1 — Revenue & launch essentials (self-hosted path)

### Take money + automate licensing
- [ ] **Integrate a payment provider** (Stripe / Paddle / Lemon Squeezy). 🔴 · L
- [ ] **Self-serve checkout → auto-mint serial.** Wire payment success → Ed25519 signed serial issuance against existing `serial_admin.py` / license authority (no manual minting). 🔴 · L
- [ ] **Trial flow** (time-limited license or feature-gated trial). 🟠 · M
- [ ] **Automated renewal + dunning** (subscription path): reminders, grace handling, failed-payment retries, revoke-on-cancel. 🟠 · M
- [ ] **Non-engineer license admin console** so sales/support can issue/revoke/extend without the loopback GUI. 🟡 · M

### Distribution friction
- [ ] **Code-sign the Windows binaries** (`DentaCare.spec` `codesign_identity` is currently `None`). Buy OV/EV cert; removes SmartScreen "unknown publisher". 🔴 · S (+ cert procurement)
- [ ] **Sign the installer** (`DentaCare-Setup.exe`) and verify clean SmartScreen pass. 🔴 · S
- [ ] **iOS build** for the Flutter app (currently `ios/` is scaffolding only; `flutter_bluetooth_serial` is Android-only — gate BT behind a platform check, ship Wi-Fi/cloud sync on iOS). 🟠 · L
- [ ] **Apple Developer enrollment + App Store / TestFlight pipeline.** 🟠 · M

### Onboarding & migration-in (highest conversion leverage)
- [ ] **Guided first-run onboarding** (activate → create clinic → seed sample data). 🟠 · M
- [ ] **Bulk patient import** (CSV/Excel from whatever the clinic uses today). Migration-in is often the make-or-break for the sale. 🟠 · L
- [ ] **Polished activation flow review** (already redesigned once — re-validate against the new payment path). 🟡 · S

---

## PHASE 2 — Trust & go-to-market

### Marketing funnel
- [ ] **Landing page** with clear positioning + social proof. 🟠 · M
- [ ] **Pricing page** matching the chosen model. 🟠 · S
- [ ] **Demo asset**: walkthrough video and/or hosted sandbox. 🟠 · M
- [ ] **Docs / help center** (setup, sync, troubleshooting, FAQ). 🟠 · M
- [ ] **SEO + positioning copy** for target segment/region. 🟡 · M

### Trust assets (conservative buyers)
- [ ] **Privacy + security page** (how data is stored, encrypted, who can access). 🟠 · S
- [ ] **Testimonials / first case study** from a pilot clinic. 🟡 · M
- [ ] **Support promise / SLA / contact channel.** 🟡 · S

---

## PHASE 3 — Engineering health (before the 2nd engineer, not after)

### Tame the monoliths
- [ ] **Extract `templates.py` (7.7k lines of inline HTML/CSS/JS) into real template + static files** (Jinja templates, static assets). 🟠 · XL
- [ ] **Blueprint `dental_clinic.py` (6.8k lines) by domain** (patients / appointments / billing / sync / licensing / cloud). 🟠 · XL
- [ ] **Adopt a migration framework** (Alembic-style versioned, reversible) to replace ad-hoc `ensure_table_column` ALTERs — critical once tenants run different versions. 🟠 · L

### CI / quality gates
- [ ] **Add Flutter tests to CI** (mobile = half the product, currently ungated). 🔴 · S
- [ ] **Add linting** (ruff/flake8 for Python, `flutter analyze` for Dart) to CI. 🟠 · S
- [ ] **Coverage gate** (enforce the 80% target). 🟡 · S
- [ ] **Dependency + secret scanning** (e.g. `pip-audit`, gitleaks, Dependabot). 🟠 · S
- [ ] **Build-the-installer smoke check** in CI. 🟡 · M

### Observability
- [ ] **Error tracking** (Sentry or equivalent) on desktop server + cloud node + mobile. 🟠 · M
- [ ] **Structured logging** (replace the ~15 ad-hoc `logging` calls with structured, leveled logs). 🟡 · M
- [ ] **Uptime / health monitoring + alerting** on the cloud node (`/healthz` already exists — wire it to a monitor). 🟠 · S

---

## PHASE 4 — Scale infrastructure (only if/when cloud SaaS path is chosen)

- [ ] **Migrate cloud tenant store from SQLite-per-clinic to Postgres** (schema-per-tenant or RLS shared schema) — adds pooling, replication, PITR. 🔴 (cloud only) · XL
- [ ] **Backup + point-in-time recovery + tested restore drill.** 🔴 (cloud only) · L
- [ ] **Horizontal scaling / load handling** for the cloud node. 🟡 · L
- [ ] **Multi-tenant ops tooling** (per-tenant metrics, tenant lifecycle, isolation audits). 🟡 · L
- [ ] **Status page.** 🟢 · S

---

## CROSS-CUTTING — Security & compliance

### Security hardening
- [x] **Add CSRF protection** to the session-authenticated Flask portal. Hand-rolled synchronizer token (`X-CSRFToken` header / hidden `csrf_token` field) validated by an `_csrf_protect` before_request hook; **broad scope** (all unsafe-method requests) exempting `X-Clinic-Token`/`Authorization` header clients (mobile/sync/vendor — header-only, never the query arg). SPA delivers the token via a `<meta>` tag + a single `window.fetch` interceptor; login + change-password forms self-validate and rotate the token on login. `CLINIC_DISABLE_CSRF` kill-switch (default enforced). See `docs/superpowers/specs/2026-06-19-csrf-protection-design.md`. 🔴 · M
- [x] **Force admin password change on first run** — the seeded `admin/admin` default is flagged (`must_change_password`) and the local/LAN portal redirects to a one-time `/change-password` screen before the SPA loads; `CLINIC_ADMIN_PASSWORD` seeds a real password and skips it. Cloud node relies on `CLINIC_ADMIN_PASSWORD` at deploy. + regression tests. 🟠 · S
- [x] **Security headers** added (`_add_security_headers` after_request: nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy; HSTS over HTTPS only). **CSP still deferred** until `templates.py` is split (everything is inline `<script>`/`<style>`). 🟡 · S
- [x] **Closed an unauthenticated destructive endpoint:** `/api/data/clear-billing` was missing from the login gate — any LAN client could wipe all billing rows. Now in `_AUTH_REQUIRED_EXACT` + regression test. 🔴 · S
- [ ] **Encryption at rest** for patient data (DB and/or disk-level). 🟠 · M

### Health-data compliance (scope to chosen market)
- [ ] **Audit log** of who-viewed/edited-which-patient (PHI access trail). 🔴 (if regulated market) · L
- [ ] **Data-processing terms / privacy policy / (HIPAA) BAA template.** 🔴 (if regulated) · M
- [ ] **Data residency answer** + retention/deletion policy. 🟠 · M
- [ ] **Breach response plan.** 🟡 · S

---

## OPERATIONS / SUPPORT

- [ ] **In-app support / feedback channel.** 🟡 · S
- [ ] **Update + rollback channel** for the desktop Windows service across customers. 🟠 · L
- [ ] **Proven backup-restore drill** (don't trust copy-the-files until restore is verified). 🟠 · M

---

## What is already solid (NOT on the to-do list — keep it)

- Offline-first architecture + LAN→cloud→Bluetooth sync ladder
- Ed25519 licensing crypto + cloud authority (expiry/grace/revoke)
- Bilingual EN/AR throughout
- Windows installer + background service
- ~438 tests / 51 suites on CI (3 Python versions)
- Solid data model: patient ledgers, odontogram, appointments, billing
- Password hashing (werkzeug PBKDF2), persisted secret key, ProxyFix, register/validate rate-limiting

---

_The core clinical product is ~85% of a great single-clinic tool. The gap to a large
launch is almost entirely in the commercial (payments/GTM), trust (compliance/security),
and scale-infra layers — not in clinical features._
