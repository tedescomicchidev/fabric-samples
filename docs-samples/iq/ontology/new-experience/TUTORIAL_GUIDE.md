# Run the Fabric IQ ontology tutorial with the Track & Trace data

This guide follows the [ontology (preview) tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-0-introduction)
step by step, replacing the Lakeshore Retail sample with the synthetic Track & Trace data in this folder.
Use the tutorial for the click paths and this guide for the names, tables, keys, relationships, rules
and questions.

**Scenario.** Marta K., Track & Trace Operations Specialist, looks after 3 factories and 4 markets. On
the morning of 25 November 2026 the ontology must help an agent connect an aggregation error on PL-02 Line 3, the
authority rejections it caused, a delayed truck to Market Beta and a stock risk there, and answer an
authority's trace request.

**Target question** (the equivalent of the tutorial's "high-priority stores in the West" question):

> Which shipments dispatched on 24 November 2026 contain shipping cases with an aggregation mismatch, which
> authority submissions were rejected because of them, and what do the maintenance log and the scanner
> telemetry of the producing line show for the same time?

The data snapshot is **2026-11-25 07:00 UTC**. Write dates explicitly in prompts. Words like "yesterday" are
resolved against the real current date.

---

## Part 0: Environment setup

Same prerequisites as the tutorial. Then:

1. **Download the sample data** from the `pmi-track-and-trace-ontology` branch: on GitHub select
   **Code > Download ZIP** and open `docs-samples/iq/ontology/new-experience`, or fetch only this folder:

   ```bash
   git clone --depth 1 --branch pmi-track-and-trace-ontology --filter=blob:none --sparse <repository URL>
   cd fabric-samples && git sparse-checkout set docs-samples/iq/ontology/new-experience
   ```
2. **Lakehouse.** Create a lakehouse named **TrackTraceLH** (keep **Lakehouse schemas** selected).
   - Upload the contents of the `lakehouse` folder to **Files**: the CSV files, and the `pack` subfolder
     with its 4 part files (use **Upload folder**, or create a `pack` folder under Files and upload
     the part files into it). Don't upload the `eventhouse` files; they go to the eventhouse. The semantic
     model is created by a notebook.
   - For each CSV file, select **... > Load to Tables > New table** and keep the defaults. Table names
     are the file names (`factory`, `production_line`, ...).
   - For the `pack` folder, select **... > Load to Tables > New table** on the **folder**: table name
     `pack`, file type CSV, header on. All the part files load into one table.
3. **Eventhouse.** Create an eventhouse named **TrackTraceEH** and open its KQL database.
   - **Get data > Local file**, new table **TraceEvent**, and select all the files in
     `eventhouse/trace_event/` at once.
   - **Get data > Local file**, new table **LineScannerTelemetry**, file `eventhouse/line_scanner_telemetry.csv`.
4. **Semantic model** (replaces `SalesReport.pbix`). In the workspace, select **Import > Notebook > From
   this computer**, choose `notebooks/create_semantic_model.ipynb`, open it and select **Run all**. It
   creates and refreshes the semantic model **TrackTraceKPIs** (table `ProductionDaily`, measures
   *Packs Commissioned*, *Aggregation Error Rate %* and *Plan Attainment %*). You don't need to attach a
   lakehouse.

## Part 1: Create the ontology

Create an ontology named **TrackTraceOntology**.

### Entity types

Create each entity type, bind it to its table and add all source columns as properties. The two
inheritance pairs mirror the tutorial's Location → Store / Distribution Center and Product → Frozen /
Perishable Product: bind the child to the same table and describe the filter in Part 2.

| Entity type | Inherits from | Data source | Entity type key (Part 3) |
|---|---|---|---|
| Factory | | TrackTraceLH > factory | factory_id |
| Production Line | | TrackTraceLH > production_line | line_id |
| Production Order | | TrackTraceLH > production_order | order_id |
| Product | | TrackTraceLH > product | sku |
| Cigarette | Product | TrackTraceLH > product | sku |
| Heated Tobacco Stick | Product | TrackTraceLH > product | sku |
| Pack | | TrackTraceLH > pack | pack_uid |
| Bundle | | TrackTraceLH > bundle | bundle_uid |
| Shipping Case | | TrackTraceLH > shipping_case | case_uid |
| Pallet | | TrackTraceLH > pallet | pallet_uid |
| Shipment | | TrackTraceLH > shipment | shipment_id |
| Warehouse | | TrackTraceLH > warehouse | warehouse_id |
| Hub | Warehouse | TrackTraceLH > warehouse | warehouse_id |
| Distributor | Warehouse | TrackTraceLH > warehouse | warehouse_id |
| Market | | TrackTraceLH > market | market_id |
| Tax Authority | | TrackTraceLH > tax_authority | authority_id |
| Authority Submission | | TrackTraceLH > authority_submission | submission_id |
| Partner | | TrackTraceLH > partner | partner_id |
| Inventory Position | | TrackTraceLH > inventory_snapshot | snapshot_id |
| Demand Forecast | | TrackTraceLH > demand_forecast | forecast_id |
| Maintenance Event | | TrackTraceLH > maintenance_log | log_id |
| Consumer Scan | | TrackTraceLH > consumer_scan | scan_id |
| Trace Event | | TrackTraceEH > TraceEvent (eventhouse) | skip |
| Scanner Telemetry | | TrackTraceEH > LineScannerTelemetry (eventhouse) | skip |

**Add the KPI entity with the ontology agent** (equivalent of the tutorial's *Sale* step). Open
**Ontology agent** in Plan mode and send:

> Create a new entity type called Line Production Day, bound to data in the ProductionDaily table from
> the TrackTraceKPIs semantic model inside this workspace.

Switch to Act mode and send *Apply the entity type plan*. Check that the three measures appear as
metrics.

### Relationship types

Create these relationship types (origin property → target property).

**Needed for the storyline:**

| Relationship | Origin entity type (property) | Target entity type (property) |
|---|---|---|
| hasLine | Factory (factory_id) | Production Line (factory_id) |
| runsOrder | Production Line (line_id) | Production Order (line_id) |
| commissionedUnder | Pack (order_id) | Production Order (order_id) |
| aggregatedIntoBundle | Pack (bundle_uid) | Bundle (bundle_uid) |
| aggregatedIntoCase | Bundle (case_uid) | Shipping Case (case_uid) |
| aggregatedIntoPallet | Shipping Case (pallet_uid) | Pallet (pallet_uid) |
| caseProducedUnder | Shipping Case (order_id) | Production Order (order_id) |
| loadedOn | Pallet (shipment_id) | Shipment (shipment_id) |
| originatesAt | Shipment (from_location) | Factory (factory_id) |
| deliversTo | Shipment (to_location) | Warehouse (warehouse_id) |
| locatedIn | Warehouse (market_id) | Market (market_id) |
| reportsShipment | Authority Submission (shipment_id) | Shipment (shipment_id) |
| submittedTo | Authority Submission (authority_id) | Tax Authority (authority_id) |
| stockedAt | Inventory Position (warehouse_id) | Warehouse (warehouse_id) |
| stockOfProduct | Inventory Position (sku) | Product (sku) |
| forecastForMarket | Demand Forecast (market_id) | Market (market_id) |
| forecastForProduct | Demand Forecast (sku) | Product (sku) |
| loggedOn | Maintenance Event (line_id) | Production Line (line_id) |
| hasScannerReading | Production Line (line_id) | Scanner Telemetry (line_id) |
| hasTraceEvent | Pack (pack_uid) | Trace Event (object_uid) |
| measuredOn | Line Production Day (line_id) | Production Line (line_id) |

**Extra context (optional):**

| Relationship | Origin entity type (property) | Target entity type (property) |
|---|---|---|
| producesProduct | Production Order (sku) | Product (sku) |
| targetsMarket | Production Order (target_market_id) | Market (market_id) |
| packOfProduct | Pack (sku) | Product (sku) |
| carriedBy | Shipment (partner_id) | Partner (partner_id) |
| regulates | Tax Authority (market_id) | Market (market_id) |
| scanOfPack | Consumer Scan (pack_uid) | Pack (pack_uid) |

Optionally add `hasTraceEvent` from Bundle, Shipping Case and Pallet as well (on `bundle_uid`,
`case_uid` and `pallet_uid` → Trace Event `object_uid`).

## Part 2: Enrich the ontology

### Entity type metadata

| Entity type | Metadata |
|---|---|
| Pack | Description: Smallest serialized saleable unit; carries a unique serial code (UID). Synonyms: UID, serial code, serialized pack, unit pack. |
| Bundle | Description: Group of packs aggregated under one bundle UID (packs_per_bundle on the product). Synonyms: carton. |
| Shipping Case | Description: Group of bundles aggregated under one case UID (bundles_per_case on the product). Synonyms: case, master case. |
| Pallet | Description: Logistics unit built from shipping cases (cases_per_pallet on the product). |
| Shipment | Description: One truck departure from a factory to a warehouse. Synonyms: consignment, load. |
| Market | Description: Market of destination; regulation_profile defines which authority submissions are required. Synonyms: market of destination, intended market. |
| Authority Submission | Description: Notification sent to a tax authority for a dispatch or arrival. Synonyms: authority submission, regulatory notification, dispatch notification, arrival notification. |
| Trace Event | Description: Track & Trace event. COMMISSION activates a UID; AGGREGATE links child_count children to the parent object_uid; DISAGGREGATE removes them; DISPATCH and ARRIVE move a pallet with a shipment; DECOMMISSION deactivates a UID; SCAN_CONSUMER is a consumer app scan. |
| Hub | Description: Filtered warehouse binding where warehouse_type = HUB. |
| Distributor | Description: Filtered warehouse binding where warehouse_type = DISTRIBUTOR. |
| Cigarette | Description: Filtered product binding where category = Cigarettes. |
| Heated Tobacco Stick | Description: Filtered product binding where category = Heated tobacco sticks. |
| Inventory Position | Additional metadata: **Days of cover** : qty_on_hand divided by (the average forecast_qty of the next 7 days for the warehouse's market and SKU × warehouse demand_share_pct / 100). Quantities are shipping cases. |

### Property metadata

| Entity type | Property | Description |
|---|---|---|
| Shipping Case | aggregation_status | COMPLETE = all expected bundles aggregated; MISMATCH = fewer bundles aggregated than expected and not corrected; REWORKED = corrected by disaggregation and re-aggregation. |
| Shipping Case | bundle_count | Bundles aggregated into the case. Compare with expected_bundle_count. |
| Pack | status | AGGREGATED (at factory), DISPATCHED (in transit), ARRIVED (at destination warehouse), DECOMMISSIONED, AGGREGATION_INCOMPLETE (its bundle was never aggregated into a case). |
| Shipment | status | PLANNED, IN_TRANSIT, DELAYED (estimated arrival more than 4 hours late), DELIVERED. |
| Inventory Position | qty_on_hand | Shipping cases on hand at the snapshot time (uom = CASE), not packs. |
| Warehouse | demand_share_pct | Share of the market's demand served by this warehouse. |
| Scanner Telemetry | read_rate_pct | Percentage of expected codes read in the 5-minute interval. |
| Product | sku | Enterprise product identifier. |

### Relationship metadata (examples)

| Relationship | Description |
|---|---|
| aggregatedIntoCase | The bundle was aggregated into this shipping case. Bundles with no case were not aggregated. |
| loadedOn | The pallet travels with this shipment. |
| reportsShipment | The submission notifies the authority about this shipment's dispatch or arrival. |
| deliversTo | Identifies the warehouse receiving the shipment. |

### Rules

| Name | Definition | Linked elements |
|---|---|---|
| Aggregation mismatch | A shipping case has an aggregation mismatch when its bundle_count is lower than the bundles_per_case of its product. | Shipping Case, Product |
| Scanner degradation | An aggregation scanner is degraded when its read rate stays below 98% for more than 15 minutes, or when its station_mode is BYPASS. | Production Line, Scanner Telemetry |
| Delayed shipment | A shipment is delayed when it departed more than 4 hours after its planned departure or its estimated arrival is more than 4 hours after its planned arrival. | Shipment |
| Submission SLA breach | An authority submission breaches its SLA when it isn't accepted by sla_due_ts (event time plus the authority's submission_sla_hours). | Authority Submission, Tax Authority |
| Supply risk | A warehouse has a supply risk for a SKU when its days of cover is below 3. A warehouse in the same market with more than 7 days of cover can transfer stock. | Inventory Position, Demand Forecast, Warehouse |
| Suspicious consumer scan | A pack is suspicious when it's scanned in two different countries within 24 hours, or when a scanned UID doesn't exist. | Consumer Scan, Pack |

## Part 3: Explore the ontology

1. Define the entity type keys from the table in Part 1. Skip Trace Event, Scanner Telemetry and Line
   Production Day (unsupported source types for the graph).
2. **Home > Manage > Graph**: project at least Factory, Production Line, Production Order, Pack, Bundle,
   Shipping Case, Pallet, Shipment, Warehouse, Distributor, Market and Authority Submission with their
   relationships, then **Materialize**.
3. Path query (the S4 trace):
   - Start node: **Pack**, filter `pack_uid = PK-PL-01-6U4NNZG5`
   - End node: **Warehouse**
   - Max hops: **5**

   Expected path: Pack → Bundle `BU-PL-01-JTMDKKKA` → Shipping Case `CS-PL-01-7RSZRXNH` → Pallet
   `PAL-PL-01-2LNFLRR2` → Shipment `SHP-20261120-PL01-BETD2-E` → Warehouse `WH-BET-D2`.
4. Path query (the S1 impact): start **Production Line** `line_id = PL-02-L3`, end **Authority
   Submission**, max hops 5. Look for the two rejected submissions SUB-000163 and SUB-000167.

## Part 4: Ask the ontology agent

Ask these in Plan mode. The expected answers come from the generated data.

| Scene | Question | Expected answer |
|---|---|---|
| 1 Morning briefing | How many packs were commissioned per factory on 24 November 2026, how many shipping cases had an aggregation mismatch, and which authority submissions were rejected? | PL-02-L3 has 120 mismatched cases; SUB-000163 and SUB-000167 were rejected by Gamma. |
| 2 Anomaly drill-down | Why did production line PL-02-L3 have an aggregation mismatch on 24 November 2026? How many cases were affected? | 120 cases between 06:42 and 18:36 UTC. Scanner fault logged 06:20, station in bypass from 06:38, repaired 18:40; telemetry shows the case scanner degraded. |
| 3 Delayed shipment | Which shipments to Market Beta are delayed, and how many pallets, shipping cases and packs do they carry? | `SHP-20261123-PL01-BETD1`: departed 26 h late, 12 pallets, 232 cases, 11,600 packs. |
| 4 Authority request | Provide the full trace of pack PK-PL-01-6U4NNZG5. | Bundle, case, pallet, shipment and warehouse as in Part 3; dispatch and arrival submissions accepted. |
| 5 Supply risk | Which warehouses in Market Beta have less than 3 days of cover for SKU-03, and which warehouse in the same market could transfer stock? | WH-BET-D1: 76 cases, 2.1 days, inbound on the delayed truck. WH-BET-D2: 11.5 days; about 108 cases can move while keeping 7 days. |
| 6 Consumer scans | Which packs were scanned by consumers in two different countries within 24 hours? | `PK-PL-01-DQUGV4TG` (XB, then XZ 13.6 hours later). |
| Target question | (see the top of this guide) | `SHP-20261124-PL02-GAMH1` and `SHP-20261124-PL02-GAMH1-E`; submissions SUB-000163 and SUB-000167; scanner fault and bypass on PL-02-L3. |

## Beyond the tutorial

- `work-context/` holds the emails, Teams messages and SOPs for the Work IQ part of the storyline
  (scenes 1, 3 and 4). The `.eml` files can be opened in Outlook; `emails.json` lists which are relevant.
- `README_data.md` lists row counts, where each scenario lives and the design choices of the data set.
