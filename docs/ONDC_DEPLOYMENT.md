# Secure deployment architecture

`docker-compose.production.yml` is provider-neutral, production-like scaffolding. Caddy terminates HTTPS and routes public endpoints; React is served by unprivileged Nginx; FastAPI runs separately; the maintenance worker recovers callbacks and catalog jobs; PostgreSQL is attached only to an internal network with persistent storage and has no host port.

Create `backend/.env.production` and `secrets/postgres_password.txt` outside Git. Set `DEPLOYMENT_ENVIRONMENT=preprod`, strong `ADMIN_API_TOKEN`, matching database URL, explicit HTTPS CORS origin, ONDC identity/URLs/keys, official PreProd lookup URL, supported city and `ONDC_EXTERNAL_NETWORK_ENABLED=true`. Set `PUBLIC_DOMAIN` and database nonsecret values in the operator environment.

Validate without starting:

```powershell
docker compose -f docker-compose.production.yml config
```

After infrastructure/security approval:

```powershell
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml ps
```

Provide at least two API instances behind a managed load balancer for high availability; this sample Compose is single-host. Restrict admin routes at the proxy/VPN in addition to application tokens. Configure centralized logs/metrics, resource limits, image scanning, patching, outbound allowlists and alerting. The callback/catalog worker is restart-safe because work is persisted in PostgreSQL.

Back up with encrypted `pg_dump --format=custom` to access-controlled storage, record checksums/retention, and regularly restore into an isolated database with `pg_restore`. Never place dumps in Git. Test recovery before onboarding and before schema/key changes.
