# Security, Privacy & Compliance Guardrails

We hold passports, CNICs, bank statements and photos, a prime target for fraudsters. Treat this as a bank-grade data problem from day one.

## Documents & PII
- Supabase Storage bucket `documents` is private. Access only through API-issued signed URLs (≤ 5 min) after ownership/role check.
- Passport numbers and CNICs encrypted at application level (`*_enc` columns, AES-GCM, key from `DOCS_ENCRYPTION_KEY`, rotate-ready with key id prefix).
- Never log document contents, passport numbers, CNICs, or full bank statements. Redact in error tracking (Sentry `before_send`).
- LLM calls with documents: send only what the task needs; do not include documents in analytics or prompt logs.
- Retention: delete documents N days after case completion (configurable, default 90) unless user opts to keep them; deletion logged.
- Users can download and delete their data from Account.

## Access control
- RLS on every table (see DATA_MODEL.md). Tests per policy.
- Ops/admin actions only via API with role check; all ops actions logged to `case_events` (internal or user-visible as appropriate) and `audit_log`.
- Partners see only their assigned cases, only the fields they need.
- 2FA required for ops/admin/partner accounts.

## Agent safety
- `live_fetch` only on allow-listed official domains.
- Content fetched from the web is data, never instructions; strip/ignore instructions in fetched pages.
- Refuse and explain on any request to fabricate/alter documents, fake funds, fake sponsors, or misrepresent purpose of travel.
- Guarantee-language validator on all outbound text (agent, emails, templates).

## Payments
- No card data touches our servers; gateway-hosted checkout only.
- Webhook signature verification; idempotency keys on payment and booking calls.

## Compliance (to confirm with a lawyer before launch)
- Pakistani travel agency licensing for ticketing; Umrah operator registration; OEP licence before any work-visa service.
- Destination-country rules on paid immigration advice (UK, Canada, Australia, NZ) — MVP gives general information + document prep for visit visas; regulated advice routes to licensed advisers in future.
- Pakistan data protection requirements (track the Personal Data Protection Bill status).
- Terms of Service + Privacy Policy in English and Urdu, explicit "we do not guarantee visas" clause.
