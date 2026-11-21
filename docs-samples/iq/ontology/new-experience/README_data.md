# Track & Trace demo data set

All data in this folder is **synthetic**. Factories, brands, markets, tax authorities, partners, people
and identifiers are fictional. No real company, vendor, factory, market, customer or tax-authority data
is used.

| Setting | Value |
|---|---|
| Data snapshot (as-of) | **2026-11-25 07:00 UTC** (08:00 in Krakow on the demo day) |
| "Yesterday" in the storyline | **Tuesday 24 November 2026** |
| Period | 27 Oct 2026 to 25 Nov 2026 (30 days) |
| Unit-level window (packs and bundles) | production from **2026-11-20 00:00 UTC** onwards |
| Timestamps | ISO-8601, UTC |
| Encoding | UTF-8 CSV with a header row |
| Seed | `20261125` (same seed and as-of always give identical files) |

## Row counts

| Table | File | Rows | Notes |
|---|---|---:|---|
| `factory` | lakehouse/factory.csv | 3 | 3 fictional factories |
| `production_line` | lakehouse/production_line.csv | 12 | 4 lines per factory |
| `product` | lakehouse/product.csv | 8 | 8 fictional brands, hierarchy ratios per SKU |
| `market` | lakehouse/market.csv | 4 | Market Alpha to Delta |
| `tax_authority` | lakehouse/tax_authority.csv | 4 | one per market, with submission SLA |
| `warehouse` | lakehouse/warehouse.csv | 6 | hubs and distributors, with share of market demand |
| `partner` | lakehouse/partner.csv | 5 | carriers, 3PL, customs broker |
| `production_order` | lakehouse/production_order.csv | 290 | one order per line and production day |
| `pack` | lakehouse/pack/ (4 part files) | 143,842 | unit-level window only |
| `bundle` | lakehouse/bundle.csv | 14,348 | unit-level window only |
| `shipping_case` | lakehouse/shipping_case.csv | 20,184 | full 30 days |
| `pallet` | lakehouse/pallet.csv | 1,139 | full 30 days |
| `shipment` | lakehouse/shipment.csv | 124 | full 30 days plus the next planned departures |
| `authority_submission` | lakehouse/authority_submission.csv | 170 | ACCEPTED / REJECTED / PENDING |
| `inventory_snapshot` | lakehouse/inventory_snapshot.csv | 900 | daily at 06:00 UTC, in shipping cases |
| `demand_forecast` | lakehouse/demand_forecast.csv | 817 | 30 days back and 14 days ahead, in shipping cases |
| `maintenance_log` | lakehouse/maintenance_log.csv | 57 | root cause for S1 |
| `consumer_scan` | lakehouse/consumer_scan.csv | 916 | VALID / UNKNOWN / DUPLICATE |
| `trace_event` | eventhouse/trace_event/ (5 part files) | 182,893 | COMMISSION, AGGREGATE, DISAGGREGATE, DISPATCH, ARRIVE, DECOMMISSION, SCAN_CONSUMER |
| `line_scanner_telemetry` | eventhouse/line_scanner_telemetry.csv | 20,736 | 5-minute readings for the last 72 hours |
| `production_line_daily` | semantic-model/production_line_daily.csv | 290 | data of the TrackTraceKPIs semantic model (embedded in the notebook) |

Work context: 26 emails in `work-context/emails/` (index in `emails.json`,
7 relevant and 19 noise),
15 Teams messages in `work-context/teams_messages.json` and 2 SOPs in `work-context/sop/`.

## Where each seeded scenario lives

| ID | Scenario | Where to find it |
|---|---|---|
| S1 | **Aggregation mismatch**, PL-02 Line 3, 24 Nov | `shipping_case`: 120 cases with `aggregation_status = MISMATCH` on line `PL-02-L3` (86 missing 1 bundle, 34 missing 2), created 06:42 to 18:36 UTC, order `PO-20261124-PL02L3` (SKU-02 for Market Gamma). `bundle`: 154 bundles with `status = NOT_AGGREGATED` and no case; `pack`: their 1,540 packs have `status = AGGREGATION_INCOMPLETE`. `maintenance_log`: `SCANNER_FAULT` at 06:20, bypass mode at 06:38, `REPAIR` at 18:40 UTC. `LineScannerTelemetry`: `CASE_AGGREGATION` station `DEGRADED` / `BYPASS` in the same window. The affected cases left on `SHP-20261124-PL02-GAMH1` (DELIVERED, 44 of 100 cases affected), `SHP-20261124-PL02-GAMH1-E` (IN_TRANSIT, 76 of 100 cases affected). |
| S2 | **Delayed shipment** to Market Beta | `shipment` `SHP-20261123-PL01-BETD1` (status `DELAYED`): planned departure 2026-11-23 14:00 UTC, actual 2026-11-24 16:00 UTC (**26 h late**), estimated arrival 2026-11-25 14:00 UTC instead of 2026-11-24 08:00 UTC. It carries 12 pallets, 232 cases and 11,600 packs (SKU-01: 1 pallet / 20 cases, SKU-03: 7 pallets / 131 cases, SKU-05: 1 pallet / 20 cases, SKU-07: 3 pallets / 61 cases). Partner email from Northgate Haulage quotes the shipment ID. |
| S3 | **Authority rejection**, Market Gamma | `authority_submission` `SUB-000163` and `SUB-000167`: `REJECTED`, `rejection_code = MISSING_AGGREGATION_DATA`, for the two S1 shipments above. Gamma's SLA is 4 hours, so both are in breach. They are the only unresolved rejections. |
| S4 | **Full trace request** | Pack **`PK-PL-01-6U4NNZG5`** (SKU-01): commissioned 2026-11-20 06:54 UTC on `PL-01-L1` (order `PO-20261120-PL01L1`) → bundle `BU-PL-01-JTMDKKKA` → case `CS-PL-01-7RSZRXNH` → pallet `PAL-PL-01-2LNFLRR2` → shipment `SHP-20261120-PL01-BETD2-E` (dispatched 2026-11-20 21:49 UTC, arrived 2026-11-21 15:31 UTC) → `WH-BET-D2` Beta South Distributor. Dispatch and arrival submissions ACCEPTED. The Beta Revenue and Stamp Office email asks for this trace. |
| S5 | **Supply risk**, Market Beta | `inventory_snapshot` 25 Nov: `WH-BET-D1` / SKU-03 has 76 cases on hand = **2.1 days** of cover (forecast share 36 cases/day); its replenishment of 131 cases is on the delayed S2 truck. `WH-BET-D2` / SKU-03 has 276 cases = **11.5 days** (surplus). No other warehouse/SKU is below 3 days. |
| S6 | **Consumer scan anomaly** | `consumer_scan`: pack `PK-PL-01-DQUGV4TG` scanned VALID in XB (Beta City) at 2026-11-24 08:46 UTC and again in XZ (Port Zephyr, 8,940 km away) at 2026-11-24 22:23 UTC → `DUPLICATE`. 14 further scans have `UNKNOWN` (codes that don't exist). |

## Data-quality rules (checked by `generator/validate_data.py`)

- Every active pack belongs to exactly one bundle. Exceptions: decommissioned packs (QA rejects removed
  before bundling) and the S1 packs, whose bundles were never aggregated into a case.
- Every bundle belongs to exactly one case, except the S1 bundles with `status = NOT_AGGREGATED`.
- `bundle_count` on a case equals its bundle rows. `case_count` on a pallet equals its case rows.
- Timestamps follow the logical order COMMISSION < AGGREGATE (bundle < case < pallet) < DISPATCH < ARRIVE,
  and no event is later than the data snapshot.
- The KPI table (`production_line_daily`) matches the unit-level rows for every order in the unit-level window.

## Design choices to know before you demo

These choices keep the files small enough for browser uploads and Git, while keeping the storyline
numbers from the use case.

1. **Unit-level window.** Packs, bundles and their COMMISSION and bundle AGGREGATE events exist for
   production from 20 Nov 2026 onwards (the five days the storyline uses). Shipping cases,
   pallets, shipments, submissions, inventory, forecasts and KPIs cover the full 30 days. Older cases
   carry their aggregated `bundle_count`, but no bundle rows. Ask pack-level questions about the last
   five days only.
2. **Scale.** 143,842 packs instead of about 500,000. With 120 affected cases in one line-day (S1),
   500,000 packs over 30 days and full pack-level detail can't all be true at plausible ratios. The
   generator keeps S1 and the other storyline numbers exact.
3. **Hierarchy ratios are demo-scaled.** 10 packs per bundle (a carton), but 4 to 5 bundles per case and
   20 to 25 cases per pallet, instead of the typical 50 and 40. Line speeds are round numbers
   (3, 5 or 10 cases per hour), not real speeds.
4. **Units.** `inventory_snapshot.qty_on_hand`, `qty_in_transit` and `demand_forecast.forecast_qty` are in
   **shipping cases** (`uom = CASE`). `production_order.planned_qty` and `produced_qty` are in packs.
   Warehouse-level demand is market forecast × `warehouse.demand_share_pct`.
5. **Renamed or added columns.** `date` became `snapshot_date` / `forecast_date`, and `type` became
   `warehouse_type` / `partner_type` / `maintenance_type`. Surrogate keys `snapshot_id` and `forecast_id`
   were added because ontology entity keys must be a string or an integer. A few helper columns were added,
   such as `shipment.estimated_arrival`, `shipping_case.expected_bundle_count` and
   `authority_submission.sla_due_ts`.
6. **Brand names.** "Alpine Silver" from the brief was replaced with **Glacier Silver**, because Alpine
   is an existing tobacco brand name.
7. **Relative dates.** The data is dated around 25 Nov 2026. If you rehearse on another day, the
   agents interpret "yesterday" as the real yesterday. Use explicit dates in prompts, or regenerate
   with `--as-of` set to another Wednesday at 07:00 UTC.

## Regenerate and validate

```bash
cd generator
python generate_data.py                 # rewrites the data folders, README_data.md and tutorial/
python validate_data.py                 # checks S1-S6 and the data-quality rules
python generate_data.py --as-of 2026-12-02T07:00:00Z   # same storyline one week later
```

Python 3.9 or later. It uses only the standard library.
