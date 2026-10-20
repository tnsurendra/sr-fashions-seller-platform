
# ONDC boundary

Retail B2C 1.2.5 / ONDC:RET12 / Inventory Seller Node. The existing merchant database remains independent from protocol wire models.

Publication side tables and internal APIs compose the existing PublicationProfile; the mapper retains ORM prices/variants/stock as authoritative. Discovery separates routing, validation, signatures, Registry lookup, catalog translation, durable replay/outbound state and asynchronous signed callbacks.

Read [discovery](../../../docs/ONDC_DISCOVERY.md), [security](../../../docs/ONDC_SECURITY.md), [source selection](../../../docs/ONDC_SPECIFICATION.md), [gap analysis](../../../docs/ONDC_GAP_ANALYSIS.md) and [validation](../../../docs/ONDC_VALIDATION.md). External HTTP defaults disabled; no registration or PreProd/Production connection has been performed.

Run tests from backend; enable ONDC_TEST_POSTGRES=1 to include isolated local PostgreSQL migration/worker tests. tests/mock_buyer.py is test/development only.
