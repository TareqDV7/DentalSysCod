# Terms of Service — TEMPLATE

> ⚠️ **This is a starting-point template, not legal advice.** Have a qualified attorney in your jurisdiction review and adapt this before publishing. Placeholders in `{{CURLY_BRACES}}` need filling in.

**Effective date:** {{EFFECTIVE_DATE}}
**Operator:** {{CLINIC_NAME}} ("we", "us", "the Operator")
**Service:** the {{PRODUCT_NAME}} cloud node at `app.{{DOMAIN}}`
**Contact:** {{SUPPORT_CONTACT_EMAIL}}

By using the Service you ("you", "the Customer") agree to these Terms. If you don't agree, don't pair a clinic with us — your local server runs fully without the cloud and these Terms don't apply.

## 1. What you get

A multi-tenant cloud mirror that:
- Stores a per-clinic SQLite database (`clinic_<id>.db`).
- Mirrors data with your local clinic server via `/api/sync/*` on a `CLINIC_CLOUD_SYNC_INTERVAL_MINUTES` cadence (default 15 min).
- Lets your paired mobile devices reach the data over the internet when they're off the clinic Wi-Fi.
- Runs automatic per-tenant database backups on the schedule documented in [`DEPLOY_CLOUD.md`](../DEPLOY_CLOUD.md).

What you don't get from the cloud node:
- The web portal — staff still sign in to their **local** server.
- Medical-image uploads — those stay local (the cloud returns 501).
- Anything beyond what's in this repository at the time of pairing.

## 2. Service level

The Service is provided **as-is**, on a best-effort basis. We aim for {{TARGET_UPTIME}} availability but make no contractual SLA at this tier. The local clinic server remains fully functional when the cloud node is unreachable — it is **not** a single point of failure for clinic operations.

Maintenance windows will be announced at least {{MAINTENANCE_NOTICE_HOURS}} hours in advance via {{NOTIFICATION_CHANNEL}} when foreseeable.

## 3. Your responsibilities

You agree:

- To use the Service only for managing a legitimate dental practice.
- To keep your clinic token, signing key, and staff passwords confidential — treat them like a bank password. If a credential is compromised, unpair from the cloud and re-pair to rotate it.
- That you (the Customer) are the **data controller** for patient records; we are the **data processor**. See the Privacy Policy.
- To obtain the patient consents required by {{APPLICABLE_LAW}} before entering their data into the system.
- Not to attempt to access other clinics' tenants, probe the cloud node for vulnerabilities outside a responsible-disclosure context, run automated scrapers, or otherwise impair the Service for other operators.
- To pay any fees agreed in writing for paid tiers. (Free-tier customers: there are no fees, but rate limits apply — see `_REGISTER_RATE_LIMIT` and similar.)

## 4. Pricing & billing

{{PRICING_DESCRIPTION_OR_FREE_BETA_NOTICE}}

We may change pricing with {{PRICING_NOTICE_DAYS}} days' notice. If you don't accept a price change, you can unpair before it takes effect — your local server keeps working.

## 5. Termination

- **By you, at any time.** Unpair from Settings → Cloud Sync. Your local server keeps your full database; we delete your tenant per the Privacy Policy retention schedule.
- **By us, with cause.** If you breach §3, fail to pay (paid tiers), or pose a security risk, we may suspend or terminate after attempting to notify you. Your data is recoverable for {{POST_TERMINATION_GRACE_DAYS}} days after termination on written request, then deleted.
- **By us, without cause.** With {{NO_CAUSE_NOTICE_DAYS}} days' written notice. You'll have time to export.

## 6. Data ownership and licensing

You own your clinic and patient data. By storing it on the Service, you grant us a non-exclusive, non-transferable license to host, transmit, back up, and process it solely as needed to provide the Service. We claim no other rights and may not use it for any other purpose.

The {{PRODUCT_NAME}} software itself is licensed under the terms in the repository's [`LICENSE`](../LICENSE) file. This Service license does not transfer ownership of the software.

## 7. Disclaimers

THE SERVICE IS PROVIDED "AS IS", WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NON-INFRINGEMENT. You acknowledge that the Service is not a backup of last resort — keep your **local** clinic server's database safe (the desktop has its own backups loop independent of the cloud).

## 8. Limitation of liability

To the maximum extent permitted by {{APPLICABLE_LAW}}, our aggregate liability arising out of or relating to the Service is limited to {{LIABILITY_CAP_DESCRIPTION}}. We are not liable for indirect, incidental, consequential, or punitive damages, including lost profits, lost goodwill, or data loss not caused by our gross negligence.

This does not limit liability we cannot limit by law (e.g., for fraud, willful misconduct, or where local consumer-protection law forbids such caps).

## 9. Indemnification

You agree to indemnify and hold us harmless from claims arising out of (a) your violation of these Terms, (b) your processing of patient data in violation of applicable law, or (c) your infringement of any third-party right.

## 10. Changes to these Terms

We may amend these Terms. Material changes will be notified at least {{TERMS_CHANGE_NOTICE_DAYS}} days in advance via {{NOTIFICATION_CHANNEL}}. Continued use after the effective date means you accept the changes.

## 11. Governing law and disputes

These Terms are governed by the laws of {{JURISDICTION}}, without regard to its conflict-of-law rules. Disputes will be resolved by {{DISPUTE_RESOLUTION_FORUM}}. Nothing in this section limits any non-waivable consumer-protection rights you have under your local law.

## 12. Miscellaneous

- **Severability:** if any clause is unenforceable, the rest stays in effect.
- **No waiver:** failure to enforce a clause once is not a waiver of future enforcement.
- **Entire agreement:** these Terms plus the Privacy Policy are the entire agreement between us regarding the Service.
- **Notices:** to you at the email on file; to us at {{SUPPORT_CONTACT_EMAIL}}.
