"""Writes the generated documentation (README.md, README_data.md) and the notebook that creates
the KPI semantic model. The tutorial pages are rendered by tutorial_docs.py. Every ID and number is taken from the generated
data, so the documents always match the files next to them."""
from __future__ import annotations

import csv
import io
import json
import os
from collections import Counter
from datetime import timezone

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
python generate_data.py                 # rewrites the data folders, README_data.md and tutorial/
python validate_data.py                 # checks S1-S6 and the data-quality rules
python generate_data.py --as-of 2026-12-02T07:00:00Z   # same storyline one week later
```

Python 3.9 or later. It uses only the standard library.
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

**Start here: [the Track & Trace ontology tutorial](tutorial/README.md).** It follows the Learn tutorial with this
data, adds the demo agents, and ends with the demo script and what each scene demonstrates.

| Folder or file | Use in the tutorial |
|---|---|
| `lakehouse/` | Upload to the lakehouse **TrackTraceLH** and load each file (and the `pack` folder) to a table |
| `eventhouse/` | Load into the eventhouse **TrackTraceEH** as tables `TraceEvent` and `LineScannerTelemetry` |
| `notebooks/create_semantic_model.ipynb` | Run in Fabric to create the semantic model **TrackTraceKPIs** (replaces `SalesReport.pbix`) |
| `notebooks/create_ontology.ipynb` | Optional: run in Fabric to create the ontology **TrackTraceOntology** of parts 1 and 2 in one step ([shortcut](tutorial/tutorial-1-2-shortcut.md)) |
| `notebooks/setup_workspace.ipynb` | Optional: run in Fabric to set up part 0 (lakehouse, eventhouse, semantic model, with the data downloaded from GitHub) and create the ontology of parts 1 and 2 in one run ([shortcut](tutorial/tutorial-0-2-shortcut.md)) |
| `semantic-model/` | Source data of that semantic model, for reference. Don't upload it. |
| `work-context/` | Emails, Teams messages and SOPs for the Work IQ part of the demo |
| [`tutorial/`](tutorial/README.md) | **The tutorial**: parts 0 to 4 follow the Learn ontology tutorial with this data, part 5 builds the demo agents, part 6 is the demo script with what each scene demonstrates |
| [`README_data.md`](README_data.md) | Row counts, seeded scenarios S1-S6 and design choices |
| `generator/` | `generate_data.py` (fixed seed), `validate_data.py`, the tutorial templates, `ontology_spec.py` (the ontology that the notebooks create) and `setup_notebook.py` (writes the setup notebook with its data manifest) |

Data snapshot: **{_t(g.as_of)}**. To move the storyline to another week, run
`python generator/generate_data.py --as-of <a Wednesday>T07:00:00Z`.
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
