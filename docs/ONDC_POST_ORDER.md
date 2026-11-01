# ONDC RET12 post-order operations

Implemented and locally verified October 30, 2026 for the constrained Retail B2C 1.2.5 `ONDC:RET12` Delivery/P2P profile. This is not ONDC certification.

## Supported protocol operations

- `POST /status` authenticates the Buyer App, enforces ownership and replay protection, ACKs, and durably sends signed `/on_status` with the current order audit snapshot.
- `POST /cancel` supports the contract-evidenced Buyer cancellation reason `006` for fulfillment TAT breach. It requires the quoted fulfillment ID, rejects pre-breach and post-pickup cancellation, atomically restores inventory once, records zero configured cancellation charge and a refund obligation when the signed Buyer payment state was `PAID`, then sends `/on_cancel`.
- `POST /update` supports the evidenced `update_target=item`, fulfillment type `Return`, `return_request`, and reason `003`. Returns require a delivered order, returnable product, an open catalog return window and a quantity no larger than the purchased quantity. It persists `Return_Initiated` and sends `/on_update`.

Unknown orders and Buyer ownership mismatches both return official Seller error `30018` without disclosing another Buyer's order. Invalid return and cancellation requests use official codes `30005`, `30012` or `30014`. All callbacks use existing durable leases, signing and retry behavior.

## State model

Internal state is separate from wire state:

| Internal | Order state | Fulfillment state |
| --- | --- | --- |
| accepted | Accepted | Pending |
| packed | In-progress | Packed |
| ready_for_pickup | In-progress | Packed plus official `ready_to_ship=yes` tag |
| picked_up | In-progress | Order-picked-up |
| delivered | Completed | Order-delivered |
| fulfillment_failed | In-progress | Delivery-failed |
| cancelled | Cancelled | Cancelled |

Authenticated admin transitions enforce a narrow P2P graph. Every changed state appends an immutable, idempotency-keyed history row with actor, source and timestamp. Repeating the same key is safe; invalid jumps return HTTP 409.

## Returns and financial audit

Return decisions are internal authenticated actions producing `Return_Approved` or `Return_Rejected`. Reverse pickup, inspection, liquidation, return-delivered, replacement/exchange and actual refund execution remain disabled because their complete operational inputs and verified reason/policy profiles are not configured.

Financial events are immutable Decimal rows with currency, amount, event type, status, idempotency key, optional transaction reference and timestamp. Confirmation records expected payment and a signed-Buyer-reported payment as `recorded`, explicitly not as bank settlement confirmation. Cancellation records cancellation charge and refund obligation. No live payment, settlement or refund is performed, and no reference or completed status is fabricated.

## Administration and privacy

State-changing endpoints require `X-Admin-Token` matching backend-only `ADMIN_API_TOKEN`. If unset, they fail closed with 503; invalid/missing tokens return 401. The React Orders page accepts a token only in component memory and does not persist or bundle it. Read APIs omit billing/contact data while showing items, states, history, return decisions and financial-event status.

## Unsupported and UNVERIFIED

Seller force cancellation, reason codes beyond the locally evidenced `006`/`003`, cancellation fees other than the explicitly recorded zero-charge local profile, partial refund execution, exchange/replacement, reverse logistics, settlement confirmation and broader routing/payment profiles are unsupported. Live Registry/gateway/callback acceptance and external reason-code governance remain UNVERIFIED.
