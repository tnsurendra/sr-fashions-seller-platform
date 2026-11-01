# ONDC PreProd readiness

This repository is locally prepared for an operator-controlled PreProd exercise. It is not registered, deployed, certified, whitelisted or proven interoperable.

## Readiness gate

1. Obtain organization approval, an ONDC Portal account and PreProd subscriber-ID whitelisting.
2. Provision a public FQDN whose hostname exactly equals `ONDC_SUBSCRIBER_ID`, valid HTTPS/OCSP, and protected hosting.
3. Generate separate Ed25519 and X25519 key pairs in an approved secret manager. Never use local fixture/development keys.
4. Configure every required backend variable and run `python -m app.ondc.onboarding.cli`. It performs no network call by default.
5. After deployment approval, run the CLI with `--check-public` to GET only the configured HTTPS verification page.
6. Execute mock Buyer, failure/retry, migration, smoke and production-build gates. Preserve redacted logs and payload evidence.
7. Have an operator review the redacted Seller App payload. Add the real legal/GST/PAN/signatory fields outside source control.
8. Only after separate explicit approval, submit through the authorized ONDC workflow. This repository has no automatic `/subscribe` sender.
9. Verify the resulting record with signed PreProd `/v2.0/lookup`, then run Workbench/log validation. Passing locally is not certification.

Required endpoints are `https://<subscriber-id>/ondc-site-verification.html`, the configured relative callback plus `/on_subscribe`, and the protocol routes. Production remains disabled in application configuration.

## Local evidence command

```powershell
cd backend
$env:ONDC_TEST_POSTGRES='1'
.\.venv312\Scripts\python.exe -m pytest -q --basetemp=.pytest-preprod
.\.venv312\Scripts\python.exe -m alembic current
.\.venv312\Scripts\python.exe -m alembic check
.\.venv312\Scripts\python.exe -m app.ondc.onboarding.cli
```

Remaining external blockers: organization details, subscriber ID/domain, SSL/OCSP, cities, keys, Portal access, whitelisting, infrastructure approval, Registry response and external validation evidence.
