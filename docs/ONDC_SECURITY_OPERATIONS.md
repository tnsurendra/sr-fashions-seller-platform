# ONDC security operations

## Controls

- Nonlocal administrative mutations require the operator token; state-changing ONDC lifecycle endpoints already fail closed. Read endpoints containing operational data should also be restricted by the reverse proxy/VPN.
- CORS requires explicit origins; PreProd/production accept HTTPS origins only. Secrets stay backend-only.
- Requests have a 1 MiB default limit, process-local rate limiting, correlation IDs, structured request logs without bodies/query strings, and safe database errors.
- `/livez` is process liveness; `/readyz` verifies PostgreSQL. Authenticated `/internal/metrics` exposes HTTP counts, callback delivery/failure, Registry lookup outcomes and queue backlog.
- Trust forwarded headers only from the reverse proxy. Do not expose Uvicorn directly.

The process-local limiter is defense in depth, not a distributed perimeter control. Configure rate limits/WAF at the load balancer for multi-instance deployment. The operator token is a minimal single-role permission boundary; use an identity-aware proxy for named users, MFA and viewer/operator/auditor roles before broader administration.

## Incident and key operations

Alert on readiness failure, callback/catalog backlog age, repeated Registry failures, 401/413/429 spikes, worker restarts and database capacity. Integrate an error-monitoring SDK only with request-body and header scrubbing. Never send Authorization, admin tokens, keys, challenge plaintext, billing/payment fields or unnecessary customer data.

For key rotation, generate a new version in the secret manager, validate public formats, prepare an authorized amendment, retain the old private key through the overlap window, confirm Registry lookup, deploy the new signer, monitor, then revoke according to policy. Never rotate automatically from this repository.

Git audit found local `.env` files ignored and no tracked private-key file. `.gitignore` excludes `.env*`, `.ondc-keys`, private keys, PEM/P12/PFX, backups, dumps and `secrets/`. Before committing, review all Prompt 3–5 changes together and use a secret scanner. Do not commit or push without approval.
