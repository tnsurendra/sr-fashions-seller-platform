# Durable ONDC catalog synchronization

The existing one-time incremental pull is extended with the official `catalog_inc` `mode=start|stop` behavior for local mocked Buyers.

## Design

An authenticated `mode=start` search upserts a durable subscription keyed by Buyer App and transaction ID. `start_time` is used when supplied; otherwise the signed context timestamp becomes the cursor. `mode=stop` marks the matching subscription stopped. The interval is a local operational setting (`ONDC_CATALOG_SYNC_INTERVAL_SECONDS`, 60–1800, default 300), not an invented ONDC payload field.

The scheduled maintenance command:

1. locks due active subscriptions with `SKIP LOCKED`;
2. creates a unique cursor-window publication job;
3. advances the durable subscription cursor;
4. claims jobs with compare-and-update leases;
5. builds the existing validated incremental catalog;
6. sends signed gzip `/on_search` with `X-ONDC-Search-Response: inc` only when changes exist;
7. marks delivery or schedules bounded exponential retry.

Unique subscription/window constraints prevent duplicate jobs. Expired leases permit another process to recover after restart. Status, attempts, next retry and safe failure token are visible on the ONDC Settings page. Payloads, Authorization values and customer information are not stored in job errors.

Run from `backend` with protected local configuration:

    .\.venv312\Scripts\python.exe -m app.ondc.protocol.maintenance

Schedule this command externally at least as frequently as the smallest configured interval. No in-process timer is started, avoiding duplicate schedulers across web workers.

## Boundaries

Automated tests use local/mock transports only. External networking remains disabled by default. Live Buyer subscription persistence expectations, long-running delivery behavior and ONDC operational cadence are UNVERIFIED. Dead-letter is represented by durable failed jobs with retry metadata; automated terminal abandonment is deliberately not invented.
