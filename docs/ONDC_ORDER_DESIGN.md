# ONDC RET12 order design

Verified locally October 30, 2026. Target: ONDC Retail B2C 1.2.5, `ONDC:RET12`, Seller/ISN. This is a constrained local implementation, not ONDC certification.

## Official basis and supported profile

The implementation follows the pinned official Retail B2C 1.2.5 contract and generated schemas at ONDC-RET-Specifications commit `7a9c7e6955018ae8f758c22f3f78f7af7d8def4e`. The official B2C flow examples and `Order_Select`/`Order_On_Select` schemas define the provider/location/item identifiers, quantities, Delivery fulfillment, quote breakup, billing, payment and `Created` to `Accepted` transition used here.

Supported locally: one enabled provider, one store per order, existing catalog item IDs (`SKU@store-{id}`), Delivery, one fulfillment, INR, positive integer quantities, BAP or BPP payment collection fields, and the existing store serviceability tags. Offers, customizations, split fulfillment, self-pickup purchase, purchase finance and other legal profiles are rejected or left unimplemented rather than inferred.

## Data flow

1. `/select` authenticates the buyer, validates provider/store/items/quantity/serviceability, reads current price and stock, creates or refreshes a checkout intent, persists the signed callback work, ACKs, then sends `/on_select` with a quote.
2. `/init` requires the same unexpired transaction checkout, revalidates catalog/stock/price, stores billing and fulfillment input without confirming an order, ACKs, then sends `/on_init`.
3. `/confirm` locks the checkout and inventory rows in a database transaction, revalidates the complete quote and payment amount, decrements stock, creates one order and its immutable item price/quantity snapshot, persists callback work, commits, ACKs, then sends `/on_confirm` with state `Accepted`.

All inbound actions use the existing Registry lookup, Ed25519 verification, TTL checks and durable replay key `(bap_id, domain, action, transaction_id, message_id)`. Callback delivery uses the existing leased database worker. A callback failure never rolls back an already confirmed order; retry claims the persisted callback without creating another order.

## Persistence and transaction boundaries

Migration `0004` adds:

- `ondc_catalog_publication_state` for pending/published/rejected entity state;
- `ondc_checkout_intents` for selected/initialized/confirmed transaction state and quote snapshots;
- `ondc_orders` for ONDC order identity, state, amount, fulfillment, payment and minimized billing data;
- `ondc_order_items` for variant/store/quantity/unit and total price snapshots;
- `callback_headers` on durable protocol messages for incremental catalog headers.

`transaction_id`, checkout-to-order and order/item constraints provide idempotency. PostgreSQL `SELECT ... FOR UPDATE` serializes confirmation against the inventory and checkout rows. Quantity is decremented in the same commit as order creation and callback persistence. The PostgreSQL test starts two transactions for the final unit and proves exactly one succeeds.

## Catalog lifecycle

Publication metadata writes mark provider/store/product state pending. Successful `/on_search` delivery marks pending state published; a protocol NACK records its official error code and sanitized message as rejected. Internal APIs expose state and permit recording a rejection received through an operational channel.

One-time incremental pull accepts the official `catalog_inc` `start_time`/`end_time` tags, limits the window to one day, selects changed product/variant/inventory rows, emits only changed items, and sends `X-ONDC-Search-Response: inc`. If nothing changed it ACKs without sending an empty catalog. Store metadata supports `enabled=false`; disabled stores are excluded from full publication.

Continuous incremental push `mode=start|stop` is rejected with official unsupported-feature code `40001`. A durable subscription scheduler, provider/store disable event payloads, and automated catalog/store rejection framework ingestion remain future work.

## Payment, fulfillment and privacy

The quote includes item totals and the explicitly configured store delivery charge. Store purchase publication requires an explicit official duration for fulfillment TAT. No default merchant promise is invented. Confirmation accepts only official payment status/type/collector values in the supported schema and requires the payment amount to equal the current quote.

The admin Orders response exposes order/item/amount/fulfillment/payment status and ONDC source, but omits billing/contact details. Those remain persisted because the protocol requires fulfillment and order evidence; production retention and access control are still required.

## Recovery and unresolved interoperability

Callback rows use leases and durable retry status. Identical inbound retries ACK without duplicating stock or orders. Changed bodies under reused message identifiers NACK. Checkout expiry is currently one day, matching the emitted `P1D` quote TTL.

UNVERIFIED: live receiver acceptance of the constrained callback payloads; gzip/signing ordering; Registry/gateway behavior; exact production settlement fields; real pincode/radius serviceability; continuous incremental scheduling; and external catalog rejection delivery. No Registry subscription, PreProd or Production call was made.

## Prompt 4 extension

Migration `0005` adds separate internal/protocol order state, append-only transition history, immutable financial events, return requests, catalog subscriptions and publication jobs. Signed status/cancel/update callbacks, authenticated fulfillment transitions, TAT-gated cancellation, single inventory restoration and constrained return initiation are documented in [ONDC_POST_ORDER.md](ONDC_POST_ORDER.md). Durable continuous incremental scheduling is documented in [ONDC_CATALOG_SYNC.md](ONDC_CATALOG_SYNC.md).
