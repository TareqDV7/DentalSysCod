# Legal templates

Two starting-point Markdown templates for the cloud SaaS:

- [`privacy-policy-template.md`](privacy-policy-template.md)
- [`terms-of-service-template.md`](terms-of-service-template.md)

Both are **templates, not legal advice**. Patient health data is regulated in most jurisdictions — get a qualified attorney in your jurisdiction (PDPL/KSA, Israeli PPL, HIPAA, GDPR, …) to review them before publishing.

## How to use them

1. Copy each template to a working file (e.g. `privacy-policy.md` outside this directory).
2. Fill in every `{{PLACEHOLDER}}` — search for `{{` to find them all.
3. Have your attorney review the substantive sections, especially:
   - Privacy §3 (retention), §4 (location), §6 (rights), §7 (security/breach notification)
   - TOS §5 (termination), §7 (disclaimers), §8 (liability cap), §11 (governing law)
4. Decide where to publish:
   - Public web page on the marketing site, or
   - Linked from inside the desktop portal (Settings → About → Legal), or
   - Both — common practice is one canonical source and link to it everywhere.
5. Record the effective date in the document and in a changelog.

Keep the templates here in version control as the canonical starting point. Future updates should re-derive from these, not edit the published copies directly.
