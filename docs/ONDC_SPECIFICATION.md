# Current discovery extension — October 8, 2026

Retail B2C **1.2.5** / RET12 / ISN is still the selected contract. The historical foundation-only limits below have been extended with publication persistence, signing, replay protection, mocked Registry lookup and local search/on_search. The preserved schema reconciliations and taxonomy remain unchanged. See [ONDC_SECURITY.md](ONDC_SECURITY.md) for additional official sources, signing/lookup conflicts and UNVERIFIED network behavior; [ONDC_DISCOVERY.md](ONDC_DISCOVERY.md) for current supported flow; [ONDC_VALIDATION.md](ONDC_VALIDATION.md) for 149 passing tests. No real network or onboarding activity occurred.

Revalidated October 30, 2026 (America/New_York): the official ONDC developer index still lists **B2C Retail 1.2.5 (Latest)**, the official signing guide still specifies BLAKE-512/Ed25519 signing and Registry-backed key verification, and the complete PostgreSQL-enabled local suite passes 149 tests. The foundation-era sections below are retained as implementation history; statements in them about discovery not yet being implemented do not describe the current application.

# Official ONDC source selection and supported profile

Verified on October 7, 2026 (America/New_York). This foundation targets Retail B2C **1.2.5**, ONDC:RET12, Seller, Inventory Seller Node (**ISN**). It does not enable network communication.

## Primary references

- [Official developer index](https://github.com/ONDC-Official/.github/blob/main/profile/README.md): B2C Retail 1.2.5 is Latest; developer guide branch draft-b2c-1.2.5.
- [Official Retail B2C 1.2.5 API contract](https://docs.google.com/document/d/1E2OyVXh34YNEVOnS4rO3nPVoqTO3RsG2uh-BqnSrqgY): search by city; full catalog; Fashion example; explanatory footnotes.
- [Version-pinned generated OpenAPI](https://github.com/ONDC-Official/ONDC-RET-Specifications/blob/7a9c7e6955018ae8f758c22f3f78f7af7d8def4e/api/build/build.yaml): info.version=1.2.5, Context/Ack/Error and discovery components.
- [Fashion taxonomy](https://docs.google.com/spreadsheets/d/1APAvavF_BNbTA89benAlGtv0GuFvpn2b6XXi4lSdTTw/edit#gid=623321892): exact category names, mandatory and optional category-specific attributes.
- [Seller error list](https://github.com/ONDC-Official/ONDC-RET-Specifications/blob/7a9c7e6955018ae8f758c22f3f78f7af7d8def4e/api/components/error_codes/ErrorCodes/ErrorCodes.yaml): 30000 = invalid request.

Source URLs, immutable repository revision and SHA256 digests are in backend/app/ondc/protocol/spec/provenance.json. discovery-contract.json is a verbatim structural subset of the generated schema with its referenced components. ret12-taxonomy.json was extracted from the official workbook, without renaming categories. The official fashion fixture only removes numeric Google Docs footnote markers; its version, values and fields remain intact.

## Conflicting official sources and resolution

The current Google API contract takes precedence over inconsistent generated schema fields and older examples. These reconciliations are explicit in protocol/specification.py, rather than hidden in application code. A regression test proves the current official fashion example passes the reconciled schema and fails the unmodified generated schema.

| Field | Generated schema / older reference | Current API contract used |
| --- | --- | --- |
| Protocol version | Generic branch README says 2.0.1; inherited examples contain 1.2.0 | Official latest index and API contract identify 1.2.5; context uses core_version |
| ItemQuantity available/maximum count | integer | Stringified integer (notes 150/151); out of stock maps to string 0; no default fictitious stock |
| Item/Provider/Category tags | Single TagGroup object | Array of tag groups in published payloads |
| Descriptor and search Intent tags | Missing from declared properties | Published bpp_terms, bap_terms and bap_features arrays |
| Finder fee type | Amount / Percent | amount / percent (note 25) |
| Fulfillment type | Pickup / Delivery and Pickup | Self-Pickup in current payloads; this profile supports Delivery and Self-Pickup |
| Time.range | date-time only | HHMM opening/closing time in full catalog, with RFC3339 ranges retained in reference validator |
| Rating.value | number | String rating, 1–5 with at most one decimal (notes 371/378); no rating fabricated by mapper |
| Fashion attribute group | Notes YAML sometimes says attributes | Current Fashion payload uses attribute; grouping paths are item.tags.attribute.colour and item.tags.attribute.size |
| Colour | Suggestive enum link in older notes is missing from current repository | Explicit merchant-supplied hex mapping; colour_name from ORM; no invented hex default (notes 385/386) |
| bpp_uri description | Erroneously says it shares bap_id hostname | Current contract has separate buyer/seller domains; match bpp_uri to bpp_id |
| Store days/schedule | holidays and times typed as date-time | Current fashion example uses YYYY-MM-DD holidays and HHMM times; reference validator follows these. Highlighted deprecated in current contract (note 374); mapper uses explicit timing tags |

The generated schema reconciliation is limited to differences evidenced above. It is not an official ONDC schema release or certification. JSON Schema format checks and Pydantic supported-profile checks are complementary.

## Supported discovery profile

Context uses the required official fields; IDs remain nonempty strings, not invented UUID-only restrictions (official example T1/M1). Discovery actions are search/on_search, domain RET12, country IND, protocol 1.2.5. City accepts std codes and wildcard for incoming discovery; settings require a specific std code. Syntax is checked; validity against the city/pincode directory still needs operational verification. RFC3339 timestamps require timezone. Search TTL is optional at schema level but, when supplied, must be a positive fixed duration <=30 seconds per Context documentation. Freshness validation is explicit and requires TTL; no wall-clock dependence in schema tests.

The foundation rejects unsupported/unknown fields. It supports first full discovery, apparel sold as individual units, nonempty full catalogs, positive cached provider TTLs, store events in enable state, and explicit Delivery/Self-Pickup fulfillment. Optional ratings, offers, credentials, replacement terms, incremental refresh, disabled-provider messages and other enhancements remain later work. The strict supported profile is intentionally narrower than all legal Retail B2C payloads. Wire serialization omits unset fields and uses official aliases.

Fashion attribute enums are **suggestive**, not exhaustive (note 384); custom real sizes are permitted. Mandatory attributes are checked per exact official category. Colour hex may be absent with an explicit no-hex mapping and descriptive colour_name (notes 385/386). All mandatory input enrichment is supplied by the caller; none is applied to live records.

## Mapper conventions and limits

- Seller maps to provider; Store maps to location; each inventory-backed ProductVariant/store pair maps to one item. IDs use seller-ID, store-ID, product-ID/store-ID groups and SKU@store-ID items. These are local stable opaque identifier conventions, not prescribed taxonomy.
- Product names/descriptions and brands, variant sizes/colors/prices and stock come from existing ORM models. Selling price maps to price.value; MRP maps to maximum_value; money is formatted from Decimal.
- Explicit zero stock remains a listed unavailable item. Missing inventory rows are not advertised. Stock is per store, never summed across locations. Configured per-order cap remains separate from availability; downstream ordering must verify current stock and reserve it.
- Merchant-supplied category mappings must resolve to exact official RET12 categories. No default mappings are installed. The test-only Hoodies-to-Sweatshirts mapping is an explicit fixture choice, not an automatic or ONDC-prescribed classification.
- Images, GPS, structured address/pincode, hours, country-of-origin, gender/fabric/size-chart and category-specific attributes, manufacturer/packer disclosures, contact, consumer care, return/cancellation/COD/shipping policies, serviceability and order cap are required external publication metadata.
- Serviceability must exist for each published location/category. Only one serviceability level is allowed per location/category (note 113); type codes 10–13 are defined in note 115. This stage checks structure and pan-India IND/country; full radius/pincode/polygon geometry and city coverage validation remains a later validator gap.
- PublicationProfile is an internal input DTO, not an ONDC payload or database redesign. Mapper revalidates it and performs no writes, network calls or inventory changes. Callers should pass fully loaded ORM snapshots under a read-only/no-autoflush session; creating a PostgreSQL repeatable-read publication snapshot and incremental cursors remains future work.

## Historical foundation configuration and security

The following two paragraphs record the pre-discovery foundation state. They are superseded by the current implementation documented in ONDC_SECURITY.md and ONDC_DISCOVERY.md.

ONDCSettings reads ONDC_-prefixed backend environment variables and loads lazily. Environment defaults to local; specifying preprod/production only validates settings and makes no connections. Subscriber ID/URL/callback URL/key ID/city must be explicitly supplied. Subscriber and callback hostnames must match identity; nonlocal settings require HTTPS. Protocol/domain/role/node type are pinned to this supported profile. Optional signing private key is SecretStr, excluded from serialization and repr, and never reaches React or OpenAPI. No private key has been created, committed or used; signing itself remains unimplemented. CALLBACK_URL is a configured seller-side callback base for future services, not a substitute for the buyer callback context.bap_uri.

No ONDC routes are mounted and no registry registration or PreProd calls have occurred. ACK/NACK functions return only the required message/ack envelope and optional official error fields. Protocol errors require a published Seller App code. Validation NACKs omit rejected input and raw exception text; existing admin HTTPException/409/503 behavior is unaffected.

## Items requiring verification before integration

Confirm target onboarding version/environment and supported features with ONDC, correct city/pincode membership and public subscriber identity, approved fashion classifications, accurate enrichment/legal disclosures and fulfillment/serviceability promises. Recheck contract/schema discrepancies against future revisions. Implement authentication, signature/lookup verification and replay protection before exposing any protocol route. Passing these local tests does not establish network readiness or certification.
