"""Writes the generated documentation (README.md, README_data.md, TUTORIAL_GUIDE.md) and the
notebook that creates the KPI semantic model. Every ID and number is taken from the generated
data, so the documents always match the files next to them."""
from __future__ import annotations

import csv
import io
import json
import os
from collections import Counter
from datetime import timedelta, timezone

UTC = timezone.utc


def _t(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _n(x):
    return f"{x:,}"


# --------------------------------------------------------------------------------------------
# Notebook: create the TrackTraceKPIs semantic model (replaces SalesReport.pbix)
# --------------------------------------------------------------------------------------------
NB_CODE_SETUP = r'''# Create (or update) the TrackTraceKPIs semantic model in the current workspace.
# Runs in a Fabric notebook (Python or PySpark). Uses only semantic-link (sempy), which Fabric preinstalls.
import base64, csv, io, json, time
import sempy.fabric as fabric

MODEL_NAME = "TrackTraceKPIs"
TABLE_NAME = "ProductionDaily"
WORKSPACE_ID = fabric.get_workspace_id()

INT_COLUMNS = ["planned_packs", "packs_commissioned", "packs_decommissioned", "bundles_aggregated",
               "cases_aggregated", "cases_with_mismatch", "pallets_built"]
TEXT_COLUMNS = ["factory_id", "line_id", "order_id", "sku", "target_market_id"]

rows = list(csv.DictReader(io.StringIO(DATA_CSV)))
for r in rows:
    for c in INT_COLUMNS:
        r[c] = int(r[c])
print(f"{len(rows)} rows embedded for table {TABLE_NAME}")
'''

NB_CODE_MODEL = r'''# Build the model definition (TMSL / model.bim). The table data is embedded in the Power Query
# expression, so the model needs no data source credentials and refreshes on its own.
payload_b64 = base64.b64encode(json.dumps(rows, separators=(",", ":")).encode("utf-8")).decode("ascii")
type_pairs = ['{"production_date", type date}'] + [f'{{"{c}", type text}}' for c in TEXT_COLUMNS] + \
             [f'{{"{c}", Int64.Type}}' for c in INT_COLUMNS]
m_expression = [
    "let",
    f'    Source = Json.Document(Binary.FromText("{payload_b64}", BinaryEncoding.Base64)),',
    "    AsTable = Table.FromRecords(Source),",
    f"    Typed = Table.TransformColumnTypes(AsTable, {{{', '.join(type_pairs)}}})",
    "in",
    "    Typed",
]

column_docs = {
    "production_date": "Production day (UTC).",
    "factory_id": "Factory that ran the production order.",
    "line_id": "Production line that ran the production order.",
    "order_id": "Production order (one per line and day).",
    "sku": "Product (SKU) produced.",
    "target_market_id": "Market of destination of the production order.",
    "planned_packs": "Packs planned for the order at rated line speed.",
    "packs_commissioned": "Packs whose serial code (UID) was commissioned, including decommissioned packs.",
    "packs_decommissioned": "Packs decommissioned at the line (QA rejects).",
    "bundles_aggregated": "Bundles aggregated into shipping cases.",
    "cases_aggregated": "Shipping cases aggregated.",
    "cases_with_mismatch": "Shipping cases whose aggregation was incomplete (MISMATCH) or had to be reworked (REWORKED).",
    "pallets_built": "Pallets built from the order.",
}
columns = [{"name": "production_date", "dataType": "dateTime", "formatString": "yyyy-mm-dd",
            "sourceColumn": "production_date", "summarizeBy": "none", "description": column_docs["production_date"]}]
columns += [{"name": c, "dataType": "string", "sourceColumn": c, "summarizeBy": "none", "description": column_docs[c]}
            for c in TEXT_COLUMNS]
columns += [{"name": c, "dataType": "int64", "formatString": "#,0", "sourceColumn": c, "summarizeBy": "sum",
             "description": column_docs[c]} for c in INT_COLUMNS]

measures = [
    {"name": "Packs Commissioned", "formatString": "#,0",
     "expression": "SUM('ProductionDaily'[packs_commissioned])",
     "description": "Number of packs whose serial code (UID) was commissioned on the production lines."},
    {"name": "Aggregation Error Rate %", "formatString": "0.00%",
     "expression": "DIVIDE(SUM('ProductionDaily'[cases_with_mismatch]), SUM('ProductionDaily'[cases_aggregated]))",
     "description": "Share of shipping cases with an aggregation mismatch or rework. Blank when no cases were aggregated. Target: below 0.5%."},
    {"name": "Plan Attainment %", "formatString": "0.0%",
     "expression": "DIVIDE(SUM('ProductionDaily'[packs_commissioned]), SUM('ProductionDaily'[planned_packs]))",
     "description": "Packs commissioned divided by packs planned at rated line speed."},
]

model_bim = {
    "compatibilityLevel": 1604,
    "model": {
        "culture": "en-US",
        "sourceQueryCulture": "en-US",
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "description": "Synthetic Track & Trace production KPIs per production line and day (demo data).",
        "tables": [{
            "name": TABLE_NAME,
            "description": "Daily production and aggregation KPIs per production line (one row per production order).",
            "columns": columns,
            "measures": measures,
            "partitions": [{"name": TABLE_NAME, "mode": "import",
                            "source": {"type": "m", "expression": m_expression}}],
        }],
        "annotations": [{"name": "PBI_QueryOrder", "value": json.dumps([TABLE_NAME])}],
    },
}
print("Model definition ready:", len(measures), "measures,", len(columns), "columns")
'''

NB_CODE_DEPLOY = r'''# Create the semantic model, or update its definition if it already exists.
client = fabric.FabricRestClient()


def b64(obj):
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode("ascii")


def wait_for_operation(resp, what):
    if resp.status_code in (200, 201):
        return
    if resp.status_code != 202:
        raise RuntimeError(f"{what} failed: HTTP {resp.status_code} {resp.text}")
    op_id = resp.headers.get("x-ms-operation-id")
    for _ in range(120):
        time.sleep(int(resp.headers.get("Retry-After", 5)))
        st = client.get(f"v1/operations/{op_id}").json()
        if st.get("status") == "Succeeded":
            return
        if st.get("status") == "Failed":
            raise RuntimeError(f"{what} failed: {json.dumps(st.get('error'), indent=1)}")
    raise TimeoutError(f"{what} did not finish in time")


def definition(pbism_version):
    return {"format": "TMSL", "parts": [
        {"path": "model.bim", "payload": b64(model_bim), "payloadType": "InlineBase64"},
        {"path": "definition.pbism", "payload": b64({"version": pbism_version, "settings": {}}),
         "payloadType": "InlineBase64"},
    ]}


existing = [m for m in client.get(f"v1/workspaces/{WORKSPACE_ID}/semanticModels").json().get("value", [])
            if m["displayName"] == MODEL_NAME]
last_error = None
for pbism_version in ("4.0", "1.0"):
    try:
        if existing:
            model_id = existing[0]["id"]
            r = client.post(f"v1/workspaces/{WORKSPACE_ID}/semanticModels/{model_id}/updateDefinition",
                            json={"definition": definition(pbism_version)})
            wait_for_operation(r, "Update definition")
            print(f"Updated semantic model {MODEL_NAME} ({model_id})")
        else:
            r = client.post(f"v1/workspaces/{WORKSPACE_ID}/semanticModels",
                            json={"displayName": MODEL_NAME, "definition": definition(pbism_version),
                                  "description": "Synthetic Track & Trace production KPIs (demo data)."})
            wait_for_operation(r, "Create semantic model")
            print(f"Created semantic model {MODEL_NAME}")
        last_error = None
        break
    except RuntimeError as e:
        last_error = e
        print(f"definition.pbism version {pbism_version} was not accepted, trying the next one: {e}")
if last_error:
    raise last_error
model_id = next(m["id"] for m in client.get(f"v1/workspaces/{WORKSPACE_ID}/semanticModels").json()["value"]
                if m["displayName"] == MODEL_NAME)
'''

NB_CODE_REFRESH = r'''# Refresh the model so the embedded rows are loaded.
pbi = fabric.PowerBIRestClient()
r = pbi.post(f"v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{model_id}/refreshes",
             json={"type": "full", "commitMode": "transactional", "retryCount": 1})
if r.status_code not in (200, 202):
    raise RuntimeError(f"Refresh request failed: HTTP {r.status_code} {r.text}")
for _ in range(60):
    time.sleep(5)
    latest = pbi.get(f"v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{model_id}/refreshes?$top=1").json()["value"][0]
    if latest["status"] in ("Completed", "Failed", "Disabled"):
        break
print("Refresh status:", latest["status"])
if latest["status"] != "Completed":
    raise RuntimeError(json.dumps(latest, indent=1))
'''

NB_CODE_CHECK = r'''# Check the measures. Expect PL-02-L3 on the day before the data snapshot to stand out.
df = fabric.evaluate_dax(MODEL_NAME, """
EVALUATE
TOPN(5,
    SUMMARIZECOLUMNS(
        'ProductionDaily'[production_date], 'ProductionDaily'[line_id],
        "Packs Commissioned", [Packs Commissioned],
        "Aggregation Error Rate %", [Aggregation Error Rate %]),
    [Aggregation Error Rate %], DESC)
""")
display(df)
'''


def _md_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _code_cell(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": text.splitlines(keepends=True)}


def write_notebook(g, path, columns):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for k in g.kpis:
        w.writerow([k[c] for c in columns])
    data_cell = "# Embedded copy of semantic-model/production_line_daily.csv (synthetic data)\n" \
                f'DATA_CSV = """{buf.getvalue()}"""\n'
    nb = {
        "cells": [
            _md_cell(
                "# Create the TrackTraceKPIs semantic model\n\n"
                "This notebook replaces the `SalesReport.pbix` step of the ontology tutorial. It creates a Power BI "
                "semantic model named **TrackTraceKPIs** in the current workspace, with one table "
                "(`ProductionDaily`) and three measures: **Packs Commissioned**, **Aggregation Error Rate %** and "
                "**Plan Attainment %**.\n\n"
                "The data is synthetic and embedded in the notebook. The model needs no lakehouse and no data "
                "source credentials.\n\n"
                "**Run:** import this notebook into your tutorial workspace and select **Run all**. Running it "
                "again updates the existing model.\n"),
            _code_cell(data_cell),
            _code_cell(NB_CODE_SETUP),
            _code_cell(NB_CODE_MODEL),
            _code_cell(NB_CODE_DEPLOY),
            _code_cell(NB_CODE_REFRESH),
            _code_cell(NB_CODE_CHECK),
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(nb, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


# --------------------------------------------------------------------------------------------
# README_data.md
# --------------------------------------------------------------------------------------------
def write_readme_data(g, path, counts, parts):
    f = g.facts
    s1, s2, s3, s4, s5, s6 = f["s1"], f["s2"], f["s3"], f["s4"], f["s5"], f["s6"]
    miss = Counter(c["expected_bundle_count"] - c["bundle_count"] for c in s1["cases"])
    s1_ship_rows = []
    for sid in s1["shipments"]:
        sh = g.shipment_by_id[sid]
        n = sum(1 for p in sh["_pallets"] for c in p["_cases"] if c["aggregation_status"] == "MISMATCH")
        s1_ship_rows.append(f"`{sid}` ({sh['status']}, {n} of {sh['case_count']} cases affected)")
    shp2 = s2["shipment"]
    s2_sku = ", ".join(f"{sku}: {v[0]} pallet{'s' if v[0] != 1 else ''} / {v[1]} cases"
                       for sku, v in sorted(s2["by_sku"].items()))
    s4p = s4["pack"]
    rows = [
        ("factory", "lakehouse/factory.csv", "3 fictional factories"),
        ("production_line", "lakehouse/production_line.csv", "4 lines per factory"),
        ("product", "lakehouse/product.csv", "8 fictional brands, hierarchy ratios per SKU"),
        ("market", "lakehouse/market.csv", "Market Alpha to Delta"),
        ("tax_authority", "lakehouse/tax_authority.csv", "one per market, with submission SLA"),
        ("warehouse", "lakehouse/warehouse.csv", "hubs and distributors, with share of market demand"),
        ("partner", "lakehouse/partner.csv", "carriers, 3PL, customs broker"),
        ("production_order", "lakehouse/production_order.csv", "one order per line and production day"),
        ("pack", f"lakehouse/pack/ ({len(parts['pack'])} part files)", "unit-level window only"),
        ("bundle", "lakehouse/bundle.csv", "unit-level window only"),
        ("shipping_case", "lakehouse/shipping_case.csv", "full 30 days"),
        ("pallet", "lakehouse/pallet.csv", "full 30 days"),
        ("shipment", "lakehouse/shipment.csv", "full 30 days plus the next planned departures"),
        ("authority_submission", "lakehouse/authority_submission.csv", "ACCEPTED / REJECTED / PENDING"),
        ("inventory_snapshot", "lakehouse/inventory_snapshot.csv", "daily at 06:00 UTC, in shipping cases"),
        ("demand_forecast", "lakehouse/demand_forecast.csv",
         f"30 days back and {14} days ahead, in shipping cases"),
        ("maintenance_log", "lakehouse/maintenance_log.csv", "root cause for S1"),
        ("consumer_scan", "lakehouse/consumer_scan.csv", "VALID / UNKNOWN / DUPLICATE"),
        ("trace_event", f"eventhouse/trace_event/ ({len(parts['trace_event'])} part files)",
         "COMMISSION, AGGREGATE, DISAGGREGATE, DISPATCH, ARRIVE, DECOMMISSION, SCAN_CONSUMER"),
        ("line_scanner_telemetry", "eventhouse/line_scanner_telemetry.csv",
         f"5-minute readings for the last {72} hours"),
        ("production_line_daily", "semantic-model/production_line_daily.csv",
         "data of the TrackTraceKPIs semantic model (embedded in the notebook)"),
    ]
    table = "\n".join(f"| `{t}` | {loc} | {_n(counts[t])} | {note} |" for t, loc, note in rows)
    emails = f.get("emails", [])
    teams = f.get("teams", [])
    text = f"""# Track & Trace demo data set

All data in this folder is **synthetic**. Factories, brands, markets, tax authorities, partners, people
and identifiers are fictional. No real company, vendor, factory, market, customer or tax-authority data
is used.

| Setting | Value |
|---|---|
| Data snapshot (as-of) | **{_t(g.as_of)}** (08:00 in Krakow on the demo day) |
| "Yesterday" in the storyline | **{s1['day']:%A %d %B %Y}** |
| Period | {g.period_start:%d %b %Y} to {g.A:%d %b %Y} (30 days) |
| Unit-level window (packs and bundles) | production from **{_t(g.detail_start)}** onwards |
| Timestamps | ISO-8601, UTC |
| Encoding | UTF-8 CSV with a header row |
| Seed | `{g.seed}` (same seed and as-of always give identical files) |

## Row counts

| Table | File | Rows | Notes |
|---|---|---:|---|
{table}

Work context: {len(emails)} emails in `work-context/emails/` (index in `emails.json`,
{sum(1 for m in emails if m['relevant'])} relevant and {sum(1 for m in emails if not m['relevant'])} noise),
{len(teams)} Teams messages in `work-context/teams_messages.json` and 2 SOPs in `work-context/sop/`.

## Where each seeded scenario lives

| ID | Scenario | Where to find it |
|---|---|---|
| S1 | **Aggregation mismatch**, PL-02 Line 3, {s1['day']:%d %b} | `shipping_case`: {len(s1['cases'])} cases with `aggregation_status = MISMATCH` on line `PL-02-L3` ({miss.get(1, 0)} missing 1 bundle, {miss.get(2, 0)} missing 2), created {s1['first_case_ts']:%H:%M} to {s1['last_case_ts']:%H:%M} UTC, order `{s1['order']['order_id']}` ({s1['sku']} for Market Gamma). `bundle`: {s1['orphan_bundles']} bundles with `status = NOT_AGGREGATED` and no case; `pack`: their {_n(s1['orphan_packs'])} packs have `status = AGGREGATION_INCOMPLETE`. `maintenance_log`: `SCANNER_FAULT` at {s1['fault_ts']:%H:%M}, bypass mode at {s1['bypass_ts']:%H:%M}, `REPAIR` at {s1['repair_ts']:%H:%M} UTC. `LineScannerTelemetry`: `CASE_AGGREGATION` station `DEGRADED` / `BYPASS` in the same window. The affected cases left on {", ".join(s1_ship_rows)}. |
| S2 | **Delayed shipment** to Market Beta | `shipment` `{shp2['shipment_id']}` (status `DELAYED`): planned departure {_t(shp2['planned_departure'])}, actual {_t(shp2['actual_departure'])} (**26 h late**), estimated arrival {_t(shp2['estimated_arrival'])} instead of {_t(shp2['planned_arrival'])}. It carries {shp2['pallet_count']} pallets, {shp2['case_count']} cases and {_n(s2['packs'])} packs ({s2_sku}). Partner email from Northgate Haulage quotes the shipment ID. |
| S3 | **Authority rejection**, Market Gamma | `authority_submission` {" and ".join(f"`{r['submission_id']}`" for r in s3['submissions'])}: `REJECTED`, `rejection_code = MISSING_AGGREGATION_DATA`, for the two S1 shipments above. Gamma's SLA is 4 hours, so both are in breach. They are the only unresolved rejections. |
| S4 | **Full trace request** | Pack **`{s4p['pack_uid']}`** ({s4p['sku']}): commissioned {_t(s4p['commissioned_ts'])} on `PL-01-L1` (order `{s4p['order_id']}`) → bundle `{s4['bundle_uid']}` → case `{s4['case']['case_uid']}` → pallet `{s4['pallet']['pallet_uid']}` → shipment `{s4['shipment']['shipment_id']}` (dispatched {_t(s4['shipment']['actual_departure'])}, arrived {_t(s4['shipment']['actual_arrival'])}) → `{s4['warehouse']['warehouse_id']}` {s4['warehouse']['name']}. Dispatch and arrival submissions ACCEPTED. The Beta Revenue and Stamp Office email asks for this trace. |
| S5 | **Supply risk**, Market Beta | `inventory_snapshot` {g.A:%d %b}: `WH-BET-D1` / SKU-03 has {s5['d1_row']['qty_on_hand']} cases on hand = **{s5['d1']:.1f} days** of cover (forecast share {s5['d1_daily']:.0f} cases/day); its replenishment of {s5['d1_row']['qty_in_transit']} cases is on the delayed S2 truck. `WH-BET-D2` / SKU-03 has {s5['d2_row']['qty_on_hand']} cases = **{s5['d2']:.1f} days** (surplus). No other warehouse/SKU is below 3 days. |
| S6 | **Consumer scan anomaly** | `consumer_scan`: pack `{s6['pack_uid']}` scanned VALID in XB (Beta City) at {_t(s6['t1'])} and again in XZ (Port Zephyr, 8,940 km away) at {_t(s6['t2'])} → `DUPLICATE`. 14 further scans have `UNKNOWN` (codes that don't exist). |

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
   production from {g.detail_start:%d %b %Y} onwards (the five days the storyline uses). Shipping cases,
   pallets, shipments, submissions, inventory, forecasts and KPIs cover the full 30 days. Older cases
   carry their aggregated `bundle_count`, but no bundle rows. Ask pack-level questions about the last
   five days only.
2. **Scale.** {_n(counts['pack'])} packs instead of about 500,000. With 120 affected cases in one line-day (S1),
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
7. **Relative dates.** The data is dated around {g.A:%d %b %Y}. If you rehearse on another day, the
   agents interpret "yesterday" as the real yesterday. Use explicit dates in prompts, or regenerate
   with `--as-of` set to another Wednesday at 07:00 UTC.

## Regenerate and validate

```bash
cd generator
python generate_data.py                 # rewrites the data folders, README_data.md and TUTORIAL_GUIDE.md
python validate_data.py                 # checks S1-S6 and the data-quality rules
python generate_data.py --as-of 2026-12-02T07:00:00Z   # same storyline one week later
```

Python 3.9 or later. It uses only the standard library.
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# --------------------------------------------------------------------------------------------
# TUTORIAL_GUIDE.md
# --------------------------------------------------------------------------------------------
def write_tutorial_guide(g, path):
    f = g.facts
    s1, s2, s3, s4, s5, s6 = f["s1"], f["s2"], f["s3"], f["s4"], f["s5"], f["s6"]
    shp2 = s2["shipment"]
    yday = f"{s1['day']:%d %B %Y}".lstrip("0")
    today = f"{g.A:%d %B %Y}".lstrip("0")
    s4p = s4["pack"]
    sub_ids = " and ".join(r["submission_id"] for r in s3["submissions"])
    releasable = max(0, s5["d2_row"]["qty_on_hand"] - int(round(7 * s5["d2_daily"])))
    text = f"""# Run the Fabric IQ ontology tutorial with the Track & Trace data

This guide follows the [ontology (preview) tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-0-introduction)
step by step, replacing the Lakeshore Retail sample with the synthetic Track & Trace data in this folder.
Use the tutorial for the click paths and this guide for the names, tables, keys, relationships, rules
and questions.

**Scenario.** Marta K., Track & Trace Operations Specialist, looks after 3 factories and 4 markets. On
the morning of {today} the ontology must help an agent connect an aggregation error on PL-02 Line 3, the
authority rejections it caused, a delayed truck to Market Beta and a stock risk there, and answer an
authority's trace request.

**Target question** (the equivalent of the tutorial's "high-priority stores in the West" question):

> Which shipments dispatched on {yday} contain shipping cases with an aggregation mismatch, which
> authority submissions were rejected because of them, and what do the maintenance log and the scanner
> telemetry of the producing line show for the same time?

The data snapshot is **{_t(g.as_of)}**. Write dates explicitly in prompts. Words like "yesterday" are
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
     with its {len(g.facts.get('pack_parts', [])) or 'part'} part files (use **Upload folder**, or create a `pack` folder under Files and upload
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
   - Start node: **Pack**, filter `pack_uid = {s4p['pack_uid']}`
   - End node: **Warehouse**
   - Max hops: **5**

   Expected path: Pack → Bundle `{s4['bundle_uid']}` → Shipping Case `{s4['case']['case_uid']}` → Pallet
   `{s4['pallet']['pallet_uid']}` → Shipment `{s4['shipment']['shipment_id']}` → Warehouse `{s4['warehouse']['warehouse_id']}`.
4. Path query (the S1 impact): start **Production Line** `line_id = PL-02-L3`, end **Authority
   Submission**, max hops 5. Look for the two rejected submissions {sub_ids}.

## Part 4: Ask the ontology agent

Ask these in Plan mode. The expected answers come from the generated data.

| Scene | Question | Expected answer |
|---|---|---|
| 1 Morning briefing | How many packs were commissioned per factory on {yday}, how many shipping cases had an aggregation mismatch, and which authority submissions were rejected? | PL-02-L3 has {len(s1['cases'])} mismatched cases; {sub_ids} were rejected by Gamma. |
| 2 Anomaly drill-down | Why did production line PL-02-L3 have an aggregation mismatch on {yday}? How many cases were affected? | {len(s1['cases'])} cases between {s1['first_case_ts']:%H:%M} and {s1['last_case_ts']:%H:%M} UTC. Scanner fault logged {s1['fault_ts']:%H:%M}, station in bypass from {s1['bypass_ts']:%H:%M}, repaired {s1['repair_ts']:%H:%M}; telemetry shows the case scanner degraded. |
| 3 Delayed shipment | Which shipments to Market Beta are delayed, and how many pallets, shipping cases and packs do they carry? | `{shp2['shipment_id']}`: departed 26 h late, {shp2['pallet_count']} pallets, {shp2['case_count']} cases, {_n(s2['packs'])} packs. |
| 4 Authority request | Provide the full trace of pack {s4p['pack_uid']}. | Bundle, case, pallet, shipment and warehouse as in Part 3; dispatch and arrival submissions accepted. |
| 5 Supply risk | Which warehouses in Market Beta have less than 3 days of cover for SKU-03, and which warehouse in the same market could transfer stock? | WH-BET-D1: {s5['d1_row']['qty_on_hand']} cases, {s5['d1']:.1f} days, inbound on the delayed truck. WH-BET-D2: {s5['d2']:.1f} days; about {releasable} cases can move while keeping 7 days. |
| 6 Consumer scans | Which packs were scanned by consumers in two different countries within 24 hours? | `{s6['pack_uid']}` (XB, then XZ 13.6 hours later). |
| Target question | (see the top of this guide) | `{s1['shipments'][0]}` and `{s1['shipments'][1]}`; submissions {sub_ids}; scanner fault and bypass on PL-02-L3. |

## Beyond the tutorial

- `work-context/` holds the emails, Teams messages and SOPs for the Work IQ part of the storyline
  (scenes 1, 3 and 4). The `.eml` files can be opened in Outlook; `emails.json` lists which are relevant.
- `README_data.md` lists row counts, where each scenario lives and the design choices of the data set.
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_folder_readme(g, path):
    text = f"""# Ontology tutorial sample data: Track & Trace edition

This folder holds a **synthetic Track & Trace data set** for the
[Fabric IQ ontology (preview) tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-0-introduction),
replacing the Lakeshore Retail sample. It supports a demo storyline: a Track & Trace operations
specialist uses agents over an ontology to connect aggregation errors, authority submissions,
shipments and supply-chain risk.

All data is fictional. No real company, factory, market, customer or tax-authority data is used.

| Folder or file | Use in the tutorial |
|---|---|
| `lakehouse/` | Upload to the lakehouse **TrackTraceLH** and load each file (and the `pack` folder) to a table |
| `eventhouse/` | Load into the eventhouse **TrackTraceEH** as tables `TraceEvent` and `LineScannerTelemetry` |
| `notebooks/create_semantic_model.ipynb` | Run in Fabric to create the semantic model **TrackTraceKPIs** (replaces `SalesReport.pbix`) |
| `semantic-model/` | Source data of that semantic model, for reference. Don't upload it. |
| `work-context/` | Emails, Teams messages and SOPs for the Work IQ part of the demo |
| [`TUTORIAL_GUIDE.md`](TUTORIAL_GUIDE.md) | Step-by-step mapping of the tutorial to this data set |
| [`README_data.md`](README_data.md) | Row counts, seeded scenarios S1-S6 and design choices |
| `generator/` | `generate_data.py` (fixed seed) and `validate_data.py` |

Data snapshot: **{_t(g.as_of)}**. To move the storyline to another week, run
`python generator/generate_data.py --as-of <a Wednesday>T07:00:00Z`.
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
