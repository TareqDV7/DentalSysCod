# Privacy Policy — TEMPLATE

> ⚠️ **This is a starting-point template, not legal advice.** Patient health data is regulated in most jurisdictions (PDPL in Saudi Arabia, the Israeli Privacy Protection Law, HIPAA in the US, GDPR in the EU, …). Have a qualified attorney in your jurisdiction review and adapt this before publishing. Anywhere a placeholder appears in `{{CURLY_BRACES}}`, fill it in.

**Effective date:** {{EFFECTIVE_DATE}}
**Operator:** {{CLINIC_NAME}} ("we", "us", "our")
**Contact:** {{PRIVACY_CONTACT_EMAIL}} · {{POSTAL_ADDRESS}}

## 1. What we collect

When you (the clinic operator) and your staff use the {{PRODUCT_NAME}} service, the following information is stored on our cloud node:

| Category | Examples | Source |
|----------|----------|--------|
| **Clinic identity** | Clinic name, serial number, the device tokens we issue you | You, during pairing |
| **Patient demographics** | Patient names, dates of birth, phone numbers, email addresses, postal addresses, medical-history notes you record | Your staff entering data into the local clinic system |
| **Clinical records** | Appointments, follow-up entries (procedure, tooth number, prices, discounts, payments, lab expenses, notes), treatment plans, billing records, expenses, holidays | Your staff entering data |
| **Operational logs** | Request method, path, status code, latency, IP address, your clinic ID — for security, debugging, and capacity planning | Automatically, when your local server or staff devices contact our cloud node |

We do **not** collect:
- Payment-card numbers (none flow through this service).
- The patient's own login credentials (patients have no account here — only clinic staff do).
- Browsing history outside the application.
- Location data.

## 2. Why we collect it

- **Provide the service.** Mirror your clinic's database to our cloud node so it can be reached from a phone off the clinic Wi-Fi, and so we can restore it if your local server fails.
- **Security.** Detect abuse, rate-limit registration attempts, identify suspicious access patterns.
- **Support.** Investigate problems you report — limited to the data needed to diagnose the specific issue.
- **Legal compliance.** Respond to lawful requests from authorities in {{JURISDICTION}}.

We do **not** sell your data, share it with advertisers, or use it for advertising.

## 3. How long we keep it

| Data | Retention |
|------|-----------|
| Active clinic + patient data | For as long as your account is active. |
| Per-tenant cloud backups | 20 snapshots × every 6 hours ≈ 5 days, per [`DEPLOY_CLOUD.md`](../DEPLOY_CLOUD.md) §Backups. Tunable via `CLINIC_BACKUP_RETENTION` / `CLINIC_BACKUP_INTERVAL_HOURS`. |
| Access logs | {{LOG_RETENTION_DAYS}} days, then rotated and deleted. |
| After account termination | {{POST_TERMINATION_RETENTION}}, then deleted. You may request immediate deletion at any time — see §6. |

## 4. Where it lives

Our cloud node runs on {{CLOUD_PROVIDER}} in the {{CLOUD_REGION}} region. The data never leaves that region in normal operation. If you require data residency elsewhere, contact us before signing up.

Your data is **always also stored locally** on the desktop the clinic runs on — the cloud is a mirror, not the primary copy.

## 5. Who can see it

- **You** and the staff you grant `users` table access to in the desktop portal.
- **Devices you pair** with the clinic — phones, tablets — using a clinic token that you generate and can revoke.
- **{{OPERATOR_TEAM_DESCRIPTION}}** — the engineers operating the cloud node — strictly when investigating a specific support ticket or security incident, under a documented access policy. We do not browse clinic data.
- **Law-enforcement / regulators** in {{JURISDICTION}} when compelled by a valid legal order — we will notify you unless gagged.

We do not share data with third-party processors except {{LIST_THIRD_PARTY_PROCESSORS_OR_WRITE_NONE}}.

## 6. Your rights

You may at any time:
- **Access** any data we hold about your clinic — the desktop portal already exposes this; we can also export a database dump on request.
- **Correct** inaccurate data — edit it directly in the portal, the cloud will mirror the change on the next sync.
- **Delete** your account — `POST /api/cloud/unpair` from the desktop disconnects the cloud mirror; emailing {{PRIVACY_CONTACT_EMAIL}} requests permanent deletion of cloud-stored copies (subject to backup-retention windows in §3).
- **Export** your data — request a copy in machine-readable form.
- **Withdraw consent** to specific processing where consent is the legal basis; the rest of the service may still function or may not, depending on what's withdrawn.

Send rights requests to {{PRIVACY_CONTACT_EMAIL}}; we'll respond within {{RESPONSE_DAYS}} days.

## 7. Security

- All traffic to the cloud node is over TLS (Caddy auto-HTTPS, `app.{{DOMAIN}}`).
- Clinic tokens are stored only as the cleartext token you receive on pairing — keep them secret. Rotate via Unpair → Pair-again from Settings → Cloud Sync.
- Passwords for desktop accounts are salted-hashed with `werkzeug.security`.
- The cloud node has no public file-upload surface (medical images return 501).
- We follow the principle of least privilege internally; access to production data is audit-logged.

No system is unbreakable. If we suffer a breach affecting your data, we will notify you and the relevant authority in {{JURISDICTION}} within {{BREACH_NOTIFICATION_HOURS}} hours of confirmation, as required by {{APPLICABLE_LAW}}.

## 8. Children

The system is designed to manage **patients of a dental clinic**, including children, but only the clinic staff interact with the application directly. Patient minors do not have accounts. Parental/guardian consent for storing minors' health data must be obtained by the clinic per local law before entering their records.

## 9. International transfers

Data may transit through {{CLOUD_PROVIDER}}'s global network to reach {{CLOUD_REGION}}. We rely on {{TRANSFER_MECHANISM}} for any cross-border transfer.

## 10. Changes to this policy

If we materially change how we handle data, we will update this document and notify you via {{NOTIFICATION_CHANNEL}} at least {{ADVANCE_NOTICE_DAYS}} days before changes take effect.

## 11. Complaints

If you believe we've handled your data improperly, contact {{PRIVACY_CONTACT_EMAIL}} first — we'd rather fix it directly. You may also lodge a complaint with {{DATA_PROTECTION_AUTHORITY}}.
