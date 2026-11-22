"""Writes notebooks/setup_workspace.ipynb: sets up tutorial part 0, and optionally parts 1 and 2, in one run.

The notebook downloads the sample data from this repository on GitHub and checks it against a manifest (checksums,
row counts and column types) that build_manifest() makes from the generated CSV files. Then it creates the lakehouse
and the eventhouse of part 0 and loads their tables, creates the semantic model with the cells of
create_semantic_model.ipynb, and creates the ontology with the cells of create_ontology.ipynb. It runs as the signed-in
user and needs no credentials.
"""
from __future__ import annotations

import ast
import csv
import glob
import hashlib
import json
import os
import re

import docs_templates
import ontology_notebook
import ontology_spec

SOURCE_REPO = "tedescomicchidev/fabric-samples"
SOURCE_BRANCH = "pmi-track-and-trace-ontology"
SOURCE_FOLDER = "docs-samples/iq/ontology/new-experience"
NOTEBOOK = "setup_workspace.ipynb"
LAKEHOUSE_FILES_SOURCE = "setup-source"
EVENTHOUSE_TABLES = {"TraceEvent": "eventhouse/trace_event", "LineScannerTelemetry": "eventhouse/line_scanner_telemetry.csv"}
SEMANTIC_MODEL_FILE = "semantic-model/production_line_daily.csv"

# ----------------------------------------------------------------------------------------------- manifest
_ID_COLUMN = re.compile(r"(.*_id|.*_uid|sku|.*_code)$")  # identifiers stay strings even if they look numeric
_TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$")


def infer_type(column, values):
    """Column type of the manifest: string, long, double, boolean, timestamp or date."""
    vals = [v for v in values if v != ""]
    if not vals or _ID_COLUMN.match(column):
        return "string"
    if all(re.fullmatch(r"-?\d{1,18}", v) for v in vals):
        return "long"
    if all(re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", v) for v in vals):
        return "double"
    if all(v in ("true", "false") for v in vals):
        return "boolean"
    if all(_TS.match(v) for v in vals):
        return "timestamp"
    if all(re.fullmatch(r"\d{4}-\d\d-\d\d", v) for v in vals):
        return "date"
    return "string"


def _files(root, rel):
    """A table's CSV files, relative to root: one file, or the part files of a folder."""
    if rel.endswith(".csv"):
        return [rel]
    return [os.path.relpath(p, root).replace(os.sep, "/") for p in sorted(glob.glob(os.path.join(root, rel, "*.csv")))]


def _table(root, files):
    header, rows = None, []
    for rel in files:
        with open(os.path.join(root, rel), encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            h = next(reader)
            if header is not None and h != header:
                raise ValueError(f"{rel}: header differs from the other part files")
            header = h
            rows += list(reader)
    columns = [[c, infer_type(c, [r[i] for r in rows])] for i, c in enumerate(header)]
    return {"files": files, "rows": len(rows), "columns": columns}


def build_manifest(root):
    """Files (bytes, sha256) and tables (files, rows, columns with types) of the generated data in root."""
    lakehouse = {}
    for path in sorted(glob.glob(os.path.join(root, "lakehouse", "*.csv"))):
        lakehouse[os.path.basename(path)[:-4]] = _files(root, f"lakehouse/{os.path.basename(path)}")
    for path in sorted(glob.glob(os.path.join(root, "lakehouse", "*", ""))):
        lakehouse[os.path.basename(os.path.dirname(path))] = _files(root, f"lakehouse/{os.path.basename(os.path.dirname(path))}")
    lakehouse_tables = {t: _table(root, lakehouse[t]) for t in sorted(lakehouse)}
    eventhouse_tables = {t: _table(root, _files(root, rel)) for t, rel in EVENTHOUSE_TABLES.items()}
    paths = [f for t in lakehouse_tables.values() for f in t["files"]]
    paths += [f for t in eventhouse_tables.values() for f in t["files"]] + [SEMANTIC_MODEL_FILE]
    files = {}
    for rel in paths:
        with open(os.path.join(root, rel), "rb") as fh:
            content = fh.read()
        files[rel] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    return {"files": files, "lakehouse_tables": lakehouse_tables, "eventhouse_tables": eventhouse_tables,
            "semantic_model_file": SEMANTIC_MODEL_FILE}


# ----------------------------------------------------------------------------------------------- cells
def _intro(m):
    lh = m["lakehouse_tables"]
    mb = sum(f["bytes"] for f in m["files"].values()) / 1e6
    return f"""# Set up the Track & Trace tutorial workspace (parts 0 to 2 in one run)

This notebook does the setup of tutorial part 0 in the current workspace, and then creates the ontology of parts 1
and 2, so you can go straight to part 3. It runs as you, with your Fabric sign-in: it needs no keys, passwords or
connections. The page `tutorial/tutorial-0-2-shortcut.md` describes it step by step.

**What it creates**

| Tutorial step | Item | Content |
|---|---|---|
| Part 0, Prepare the lakehouse | Lakehouse **{ontology_spec.LAKEHOUSE_NAME}**, with lakehouse schemas | The CSV files under **Files**, and {len(lh)} tables under **Tables > dbo** |
| Part 0, Prepare the eventhouse | Eventhouse **{ontology_spec.EVENTHOUSE_NAME}** | The tables **TraceEvent** and **LineScannerTelemetry** in its KQL database |
| Part 0, Create the semantic model | Semantic model **{ontology_spec.SEMANTIC_MODEL_NAME}** | The same model as `create_semantic_model.ipynb` creates |
| Parts 1 and 2 | Ontology **{ontology_spec.ONTOLOGY_NAME}** | The same ontology as `create_ontology.ipynb` creates. Set `CREATE_ONTOLOGY = False` to build it by hand instead. |

**Run**

1. Use a workspace on a Fabric capacity (an F SKU or a trial) with the tenant settings of part 0. You need the
   contributor role or higher.
1. Import this notebook into the workspace and select **Run all**. It runs on the Python or the PySpark kernel and
   doesn't need a default lakehouse. The run takes about 10 to 15 minutes, mostly waiting for the service.
1. The last cell lists the steps that are left in the ontology editor (about 10 minutes). Do them, then continue with
   tutorial part 3.

**Where the data comes from**

The notebook downloads the sample data ({mb:.0f} MB of CSV files) from the public GitHub repository set in the next cell,
and checks every file against the checksums it was made with. If the workspace can't reach GitHub, the download
cell stops with a message. Then upload the folders `lakehouse`, `eventhouse` and `semantic-model` of the sample to
**Files/{LAKEHOUSE_FILES_SOURCE}** in the lakehouse **{ontology_spec.LAKEHOUSE_NAME}** (the notebook has created it by then), set
`SOURCE = "lakehouse_files"`, and run the notebook again.

**Running it again** replaces the lakehouse tables, loads the eventhouse tables again only if their row counts differ,
and updates the semantic model. If the ontology already has entity types, the notebook stops before changing it; set
`REPLACE_EXISTING = True` to replace its whole definition.

> The data is synthetic. Ontology is in preview, and the ontology cells follow the documented definition format as
> of November 2026; see `create_ontology.ipynb`.
"""


def _settings():
    onto = [line for line in ontology_notebook.NB_SETTINGS.rstrip("\n").split("\n")[1:]
            if not line.startswith("LAKEHOUSE_NAME ")]
    return "\n".join([
        "# Settings. The defaults match the tutorial.",
        'SOURCE = "github"                        # where the sample data comes from: "github" or "lakehouse_files"',
        f'GITHUB_REPO = "{SOURCE_REPO}"',
        f'GITHUB_BRANCH = "{SOURCE_BRANCH}"',
        f'GITHUB_FOLDER = "{SOURCE_FOLDER}"',
        f'LAKEHOUSE_FILES_SOURCE = "{LAKEHOUSE_FILES_SOURCE}"  # with SOURCE = "lakehouse_files": the folder under Files in the lakehouse',
        f'LAKEHOUSE_NAME = "{ontology_spec.LAKEHOUSE_NAME}"',
        f'EVENTHOUSE_NAME = "{ontology_spec.EVENTHOUSE_NAME}"',
        "CREATE_ONTOLOGY = True                   # False stops after part 0, to build the ontology by hand in parts 1 and 2",
        "VERIFY_CHECKSUMS = True                  # False loads data files that differ from the ones this notebook was made for",
        "",
        "# Ontology (parts 1 and 2), as in create_ontology.ipynb",
    ] + onto) + "\n"


def _manifest_cell(m):
    return ("# The sample data: the files with their checksums, and the tables with their columns and types.\n"
            "# Generated from the CSV files by generator/setup_notebook.py.\n"
            "import json\n\n"
            f'MANIFEST = json.loads(r"""\n{json.dumps(m, indent=1)}\n""")\n')


HELPERS = r'''# Helpers for the Fabric REST API, OneLake and the eventhouse. They run on the Python or the PySpark kernel.
''' + ontology_notebook.NB_HELPERS + r'''import csv, hashlib, inspect, io
from datetime import date, datetime, timezone
import notebookutils
import requests

ONELAKE = "https://onelake.dfs.fabric.microsoft.com"


def find_item(kind, name):
    return next((i for i in list_items(kind) if i["displayName"] == name), None)


def create_item(kind, body, what):
    """Create a workspace item and return it as the list shows it (id, displayName)."""
    r = call("post", f"v1/workspaces/{WORKSPACE_ID}/{kind}", what, json=body)
    ok, res = wait(r, what)
    if not ok:
        raise RuntimeError(f"{what} failed: {res}")
    for _ in range(20):  # the new item can take a moment to show up in the list
        item = find_item(kind, body["displayName"])
        if item:
            return item
        time.sleep(3)
    raise RuntimeError(f"{what}: {body['displayName']} isn't listed yet. Run the notebook again in a minute.")


def onelake_headers():
    return {"Authorization": "Bearer " + notebookutils.credentials.getToken("storage"), "x-ms-version": "2023-11-03"}


def onelake_write(item_id, path, data):
    """Write a file to OneLake with the ADLS Gen2 API: create (replaces an existing file), append, flush."""
    url = f"{ONELAKE}/{WORKSPACE_ID}/{item_id}/{path}"
    steps = [("PUT", f"{url}?resource=file", None)]
    if data:
        steps.append(("PATCH", f"{url}?action=append&position=0", data))
    steps.append(("PATCH", f"{url}?action=flush&position={len(data)}", None))
    for method, target, body in steps:
        r = requests.request(method, target, headers=onelake_headers(), data=body, timeout=300)
        if r.status_code not in (200, 201, 202):
            raise RuntimeError(f"Writing {path} to OneLake failed: HTTP {r.status_code} {r.text[:500]}")


def onelake_read(item_id, path):
    r = requests.get(f"{ONELAKE}/{WORKSPACE_ID}/{item_id}/{path}", headers=onelake_headers(), timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"Reading {path} from OneLake failed: HTTP {r.status_code} {r.text[:300]}")
    return r.content


def onelake_delete(item_id, path):
    r = requests.delete(f"{ONELAKE}/{WORKSPACE_ID}/{item_id}/{path}?recursive=true", headers=onelake_headers(),
                        timeout=300)
    if r.status_code not in (200, 202, 404):
        raise RuntimeError(f"Deleting {path} in OneLake failed: HTTP {r.status_code} {r.text[:300]}")


def kusto(uri, database, kind, csl):
    """Run a KQL query (kind "query") or management command (kind "mgmt"); returns the first result table."""
    r = requests.post(f"{uri}/v1/rest/{kind}", data=json.dumps({"db": database, "csl": csl}).encode("utf-8"),
                      headers={"Authorization": "Bearer " + notebookutils.credentials.getToken("kusto"),
                               "Content-Type": "application/json; charset=utf-8"}, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(f"{csl.splitlines()[0][:100]}: HTTP {r.status_code} {r.text[:1500]}")
    return r.json()["Tables"][0]


def csv_records(path):
    """Header and records of a downloaded CSV file."""
    reader = csv.reader(io.StringIO(DATA[path].decode("utf-8"), newline=""))
    return next(reader), reader


def parse_value(text, typ):
    """A CSV field as a Python value of the manifest type. Empty fields are nulls."""
    if text == "":
        return None
    if typ == "long":
        return int(text)
    if typ == "double":
        return float(text)
    if typ == "boolean":
        return text.lower() == "true"
    if typ == "timestamp":
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    if typ == "date":
        return date.fromisoformat(text)
    return text
'''

LAKEHOUSE = r'''# Part 0, "Prepare the lakehouse" (1 of 2): create the lakehouse with lakehouse schemas, or use the existing one.
lakehouse = find_item("lakehouses", LAKEHOUSE_NAME)
if lakehouse is None:
    lakehouse = create_item("lakehouses", {"displayName": LAKEHOUSE_NAME, "creationPayload": {"enableSchemas": True},
                                           "description": "Track & Trace demo data (synthetic)."}, "Create lakehouse")
    print(f"Created the lakehouse {LAKEHOUSE_NAME}.")
else:
    lh_props = call("get", f"v1/workspaces/{WORKSPACE_ID}/lakehouses/{lakehouse['id']}", "Get lakehouse").json()
    if not (lh_props.get("properties") or {}).get("defaultSchema"):
        raise RuntimeError(f"The lakehouse {LAKEHOUSE_NAME} was created without lakehouse schemas, which the tutorial "
                           "needs. Delete or rename it, and run the notebook again.")
    print(f"Using the existing lakehouse {LAKEHOUSE_NAME}.")
LAKEHOUSE_ID = lakehouse["id"]
'''

DOWNLOAD = r'''# Get the sample data files and check them against the manifest.
def source_file(path):
    if SOURCE == "github":
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_FOLDER}/{path}"
        try:
            r = requests.get(url, timeout=120)
        except requests.RequestException as e:
            raise RuntimeError(f"Can't reach GitHub ({type(e).__name__}). If this workspace has no internet access, "
                               f"upload the sample folders to Files/{LAKEHOUSE_FILES_SOURCE} in {LAKEHOUSE_NAME} and set "
                               'SOURCE = "lakehouse_files" (see the first cell).') from e
        if r.status_code != 200:
            raise RuntimeError(f"Downloading {url} failed: HTTP {r.status_code}. "
                               "Check GITHUB_REPO, GITHUB_BRANCH and GITHUB_FOLDER.")
        return r.content
    if SOURCE == "lakehouse_files":
        try:
            return onelake_read(LAKEHOUSE_ID, f"Files/{LAKEHOUSE_FILES_SOURCE}/{path}")
        except RuntimeError as e:
            raise RuntimeError(f"{e}. Upload the folders lakehouse, eventhouse and semantic-model of the sample to "
                               f"Files/{LAKEHOUSE_FILES_SOURCE} in {LAKEHOUSE_NAME}.") from e
    raise ValueError(f'SOURCE must be "github" or "lakehouse_files", not {SOURCE!r}.')


DATA, changed = {}, []
for path, meta in MANIFEST["files"].items():
    DATA[path] = source_file(path)
    if hashlib.sha256(DATA[path]).hexdigest() != meta["sha256"]:
        changed.append(path)
where = f"GitHub ({GITHUB_REPO}, branch {GITHUB_BRANCH})" if SOURCE == "github" else f"Files/{LAKEHOUSE_FILES_SOURCE}"
print(f"Got {len(DATA)} files ({sum(map(len, DATA.values())) / 1e6:.1f} MB) from {where}.")
if changed:
    message = (f"Files differ from the ones this notebook was made for ({len(changed)} of {len(DATA)}): "
               f"{', '.join(changed[:5])}" + (", ..." if len(changed) > 5 else "") + ".")
    if VERIFY_CHECKSUMS:
        raise RuntimeError(message + " Use the notebook from the same branch as the data, or set "
                           "VERIFY_CHECKSUMS = False to load them anyway.")
    print("Warning:", message)
'''

TABLES = r'''# Part 0, "Prepare the lakehouse" (2 of 2): upload the CSV files to Files, and load each table to Tables/dbo.
# The column types are set explicitly: identifiers and texts are strings, counts are integers, times are
# timestamps (UTC), and days are dates.
for path in MANIFEST["files"]:
    if path.startswith("lakehouse/"):
        onelake_write(LAKEHOUSE_ID, "Files/" + path[len("lakehouse/"):], DATA[path])
print(f"Uploaded the CSV files to {LAKEHOUSE_NAME}/Files.")


def table_rows(spec):
    names = [c for c, _ in spec["columns"]]
    col_types = [t for _, t in spec["columns"]]
    rows = []
    for path in spec["files"]:
        header, records = csv_records(path)
        if header != names:
            raise RuntimeError(f"{path} has the columns {header}, but the manifest expects {names}.")
        rows += [tuple(parse_value(v, t) for v, t in zip(rec, col_types)) for rec in records]
    return names, col_types, rows


def delta_path(table):
    return f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/Tables/{LAKEHOUSE_SCHEMA}/{table}"


try:
    spark  # noqa: F821  (defined in PySpark notebooks)
    USE_SPARK = True
except NameError:
    USE_SPARK = False

if USE_SPARK:
    from pyspark.sql import types as sparktypes
    SPARK_TYPES = {"string": sparktypes.StringType(), "long": sparktypes.LongType(), "double": sparktypes.DoubleType(),
                   "boolean": sparktypes.BooleanType(), "timestamp": sparktypes.TimestampType(),
                   "date": sparktypes.DateType()}

    def write_table(table, names, col_types, rows):
        schema = sparktypes.StructType([sparktypes.StructField(n, SPARK_TYPES[t], True)
                                        for n, t in zip(names, col_types)])
        (spark.createDataFrame(rows, schema).write.format("delta").mode("overwrite")  # noqa: F821
         .option("overwriteSchema", "true").save(delta_path(table)))
else:  # Python notebook
    import pyarrow as pa
    from deltalake import write_deltalake
    ARROW_TYPES = {"string": pa.string(), "long": pa.int64(), "double": pa.float64(), "boolean": pa.bool_(),
                   "timestamp": pa.timestamp("us", tz="UTC"), "date": pa.date32()}
    SCHEMA_ARG = ({"schema_mode": "overwrite"} if "schema_mode" in inspect.signature(write_deltalake).parameters
                  else {"overwrite_schema": True})

    def write_table(table, names, col_types, rows):
        columns = list(zip(*rows)) if rows else [()] * len(names)
        data = pa.table({n: pa.array(list(c), type=ARROW_TYPES[t]) for n, t, c in zip(names, col_types, columns)})
        options = {"bearer_token": notebookutils.credentials.getToken("storage"), "use_fabric_endpoint": "true"}
        try:
            write_deltalake(delta_path(table), data, mode="overwrite", storage_options=options, **SCHEMA_ARG)
        except Exception as e:  # for example a table written by Spark with features that deltalake can't write
            print(f"  {table}: deltalake can't overwrite the existing table ({type(e).__name__}), so it's replaced.")
            onelake_delete(LAKEHOUSE_ID, f"Tables/{LAKEHOUSE_SCHEMA}/{table}")
            write_deltalake(delta_path(table), data, mode="overwrite", storage_options=options, **SCHEMA_ARG)


LOADED = {}
for table, spec in MANIFEST["lakehouse_tables"].items():
    names, col_types, rows = table_rows(spec)
    write_table(table, names, col_types, rows)
    LOADED[table] = len(rows)
    note = "" if len(rows) == spec["rows"] else f" (the manifest expects {spec['rows']:,})"
    print(f"  {LAKEHOUSE_SCHEMA}.{table}: {len(rows):,} rows{note}")
print(f"Loaded {len(LOADED)} tables into {LAKEHOUSE_NAME} with {'Spark' if USE_SPARK else 'deltalake'}.")
'''

EVENTHOUSE = r'''# Part 0, "Prepare the eventhouse": create the eventhouse, and load TraceEvent and LineScannerTelemetry into its
# KQL database.
eventhouse = find_item("eventhouses", EVENTHOUSE_NAME)
if eventhouse is None:
    eventhouse = create_item("eventhouses", {"displayName": EVENTHOUSE_NAME,
                                             "description": "Track & Trace demo events (synthetic)."},
                             "Create eventhouse")
    print(f"Created the eventhouse {EVENTHOUSE_NAME}.")
else:
    print(f"Using the existing eventhouse {EVENTHOUSE_NAME}.")

# The eventhouse comes with a KQL database of the same name, which can take a moment to accept commands.
KUSTO_URI, KQL_DB, last_error = None, None, None
for attempt in range(30):
    eh_props = call("get", f"v1/workspaces/{WORKSPACE_ID}/eventhouses/{eventhouse['id']}",
                    "Get eventhouse").json().get("properties") or {}
    databases = [call("get", f"v1/workspaces/{WORKSPACE_ID}/kqlDatabases/{i}", "Get KQL database").json()
                 for i in eh_props.get("databasesItemIds") or []]
    database = next((d for d in databases if d["displayName"] == EVENTHOUSE_NAME), databases[0] if databases else None)
    if eh_props.get("queryServiceUri") and database:
        for name in (database["displayName"], database["id"]):
            try:
                kusto(eh_props["queryServiceUri"], name, "query", "print 1")
                KUSTO_URI, KQL_DB = eh_props["queryServiceUri"], name
                break
            except RuntimeError as e:
                last_error = e
    if KQL_DB:
        break
    time.sleep(10)
if not KQL_DB:
    raise RuntimeError(f"The KQL database of {EVENTHOUSE_NAME} isn't ready after 5 minutes. Run the notebook again. "
                       f"Last error: {last_error}")
KQL_DB_NAME = database["displayName"]

KQL_TYPES = {"string": "string", "long": "long", "double": "real", "boolean": "bool", "timestamp": "datetime",
             "date": "datetime"}
CHUNK_CHARS = 1_000_000  # CSV characters per .ingest inline command


def kq(name):
    """KQL name: bracketed only if it isn't a plain identifier."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "['" + name + "']"


def kql_count(table):
    return kusto(KUSTO_URI, KQL_DB, "query", f"{kq(table)} | count")["Rows"][0][0]


def ingest(table, lines):
    kusto(KUSTO_URI, KQL_DB, "mgmt", f".ingest inline into table {kq(table)} <|\n" + "\n".join(lines))


EH_LOADED = {}
for table, spec in MANIFEST["eventhouse_tables"].items():
    columns = ", ".join(f"{kq(c)}:{KQL_TYPES[t]}" for c, t in spec["columns"])
    try:
        kusto(KUSTO_URI, KQL_DB, "mgmt", f".create-merge table {kq(table)} ({columns})")
    except RuntimeError as e:
        raise RuntimeError(f"{e}\nThe table {table} exists with other columns. Drop it in the KQL database "
                           f"(.drop table {table}) and run the notebook again.") from e
    count = kql_count(table)
    if count == spec["rows"]:
        print(f"  {table}: already has {count:,} rows, not loaded again")
        EH_LOADED[table] = count
        continue
    if count:
        kusto(KUSTO_URI, KQL_DB, "mgmt", f".clear table {kq(table)} data")
    batch, size, sent = [], 0, 0
    for path in spec["files"]:
        header, records = csv_records(path)
        if header != [c for c, _ in spec["columns"]]:
            raise RuntimeError(f"{path} has the columns {header}, which don't match the manifest.")
        for rec in records:
            out = io.StringIO()
            csv.writer(out, lineterminator="").writerow(rec)
            batch.append(out.getvalue())
            size += len(batch[-1]) + 1
            if size >= CHUNK_CHARS:
                ingest(table, batch)
                sent, batch, size = sent + len(batch), [], 0
    if batch:
        ingest(table, batch)
        sent += len(batch)
    EH_LOADED[table] = kql_count(table)
    if EH_LOADED[table] != sent:
        raise RuntimeError(f"{table} has {EH_LOADED[table]:,} rows after loading {sent:,}. Run the notebook again.")
    print(f"  {table}: {EH_LOADED[table]:,} rows")
print(f"Eventhouse {EVENTHOUSE_NAME}, KQL database {KQL_DB_NAME}: tables ready.")
'''

SEMANTIC_MODEL_DATA = r'''# Part 0, "Create the semantic model". The next cells are the cells of create_semantic_model.ipynb; only the data
# comes from the downloaded file instead of being embedded.
DATA_CSV = DATA[MANIFEST["semantic_model_file"]].decode("utf-8")
'''

SQL_SYNC = r'''# Wait for the SQL analytics endpoint of the lakehouse, and sync the new tables to it. The ontology binds to the
# lakehouse tables through this endpoint.
for _ in range(60):
    sql_props = ((call("get", f"v1/workspaces/{WORKSPACE_ID}/lakehouses/{LAKEHOUSE_ID}", "Get lakehouse").json()
                  .get("properties") or {}).get("sqlEndpointProperties") or {})
    if sql_props.get("provisioningStatus") == "Success" and sql_props.get("id"):
        break
    if sql_props.get("provisioningStatus") == "Failed":
        raise RuntimeError(f"The SQL analytics endpoint of {LAKEHOUSE_NAME} failed to provision. Delete the lakehouse "
                           "and run the notebook again.")
    time.sleep(10)
else:
    raise TimeoutError(f"The SQL analytics endpoint of {LAKEHOUSE_NAME} isn't ready after 10 minutes. "
                       "Run the notebook again.")
r = client.post(f"v1/workspaces/{WORKSPACE_ID}/sqlEndpoints/{sql_props['id']}/refreshMetadata", json={})
if r.status_code in (200, 201, 202):
    ok, res = wait(r, "Refresh SQL endpoint metadata")
else:
    ok, res = False, f"HTTP {r.status_code} {r.text[:300]}"
if ok:
    synced = {s.get("tableName"): s.get("status") for s in (res or {}).get("value", [])}
    failed = sorted(t for t, s in synced.items() if s == "Failure")
    print(f"SQL analytics endpoint of {LAKEHOUSE_NAME}: {sum(s == 'Success' for s in synced.values())} tables synced."
          + (f" Not synced: {', '.join(failed)}." if failed else ""))
else:
    print(f"Couldn't start the metadata sync of the SQL analytics endpoint ({str(res)[:300]}). "
          "Waiting 2 minutes for the automatic sync instead.")
    time.sleep(120)
'''

SUMMARY = r'''# Part 0 is set up. Compare the row counts with README_data.md.
print(f"Lakehouse {LAKEHOUSE_NAME}: {len(LOADED)} tables under {LAKEHOUSE_SCHEMA} with {sum(LOADED.values()):,} rows, "
      f"for example pack {LOADED.get('pack', 0):,} and shipping_case {LOADED.get('shipping_case', 0):,}.")
print(f"Eventhouse {EVENTHOUSE_NAME}: " + ", ".join(f"{t} {n:,} rows" for t, n in EH_LOADED.items()) + ".")
print(f"Semantic model {MODEL_NAME}: refreshed, with the measures Packs Commissioned, Aggregation Error Rate % and "
      "Plan Attainment %.")
if CREATE_ONTOLOGY:
    print("\nNext, the notebook creates the ontology of tutorial parts 1 and 2.")
else:
    print("\nCREATE_ONTOLOGY is False, so the notebook stops here. Continue with tutorial part 1, Create an ontology.")
'''

ONTOLOGY_HEADER = """## Parts 1 and 2: create and enrich the ontology

The next cells are the cells of `create_ontology.ipynb`. They run only if `CREATE_ONTOLOGY = True`. The last one
lists the steps that are left in the ontology editor; the page `tutorial/tutorial-1-2-shortcut.md` describes the same
steps.
"""

NEXT_STEPS = """## Next steps

1. Finish the ontology in the editor with the steps that the previous cell printed (about 10 minutes).
1. Continue with tutorial part 3, *Explore the ontology*.
1. For the demo agents, follow part 5. The Microsoft 365 parts (the emails, SOPs and Teams messages of the work
   context, the mock incident list and the Copilot Studio agent) aren't in this notebook; part 5 describes them.

If you set `CREATE_ONTOLOGY = False`, continue with tutorial part 1, *Create an ontology*, instead.
"""


def guarded(code, flag="CREATE_ONTOLOGY"):
    """Put a cell under `if flag:`. The leading comment lines stay outside, as the cell's title."""
    lines = code.rstrip("\n").split("\n")
    head = []
    while lines and lines[0].startswith("#"):
        head.append(lines.pop(0))
    body = [("    " + line) if line.strip() else "" for line in lines]
    wrapped = "\n".join(head + [f"if {flag}:"] + body) + "\n"
    # The body must mean exactly the same code, for example no multi-line string whose content would change.
    original = ast.dump(ast.parse(code))
    inner = ast.parse(wrapped).body[0]
    if not isinstance(inner, ast.If) or ast.dump(ast.Module(body=inner.body, type_ignores=[])) != original:
        raise ValueError("guarded(): the indented cell isn't equivalent to the original")
    return wrapped


def notebook_dict(root):
    m = build_manifest(root)
    md, code = ontology_notebook._md_cell, ontology_notebook._code_cell
    cells = [
        md(_intro(m)),
        code(_settings()),
        code(_manifest_cell(m)),
        code(HELPERS),
        md("## Part 0: lakehouse, eventhouse and semantic model\n"),
        code(LAKEHOUSE),
        code(DOWNLOAD),
        code(TABLES),
        code(EVENTHOUSE),
        code(SEMANTIC_MODEL_DATA),
        code(docs_templates.NB_CODE_SETUP),
        code(docs_templates.NB_CODE_MODEL),
        code(docs_templates.NB_CODE_DEPLOY),
        code(docs_templates.NB_CODE_REFRESH),
        code(docs_templates.NB_CODE_CHECK),
        code(SQL_SYNC),
        code(SUMMARY),
        md(ONTOLOGY_HEADER),
        code(ontology_notebook.spec_cell()),
        code(guarded(ontology_notebook.NB_COLUMNS)),
        code(guarded(ontology_notebook.NB_BUILD)),
        code(guarded(ontology_notebook.NB_DEPLOY)),
        code(guarded(ontology_notebook.NB_VERIFY)),
        md(NEXT_STEPS),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_text(root):
    return json.dumps(notebook_dict(root), indent=1, ensure_ascii=False) + "\n"


def write_notebook(root, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(notebook_text(root))


def tutorial_context(root):
    """Placeholders of the tutorial page tutorial-0-2-shortcut.md."""
    m = build_manifest(root)
    lh, eh = m["lakehouse_tables"], m["eventhouse_tables"]
    types = {}
    for spec in lh.values():
        for c, t in spec["columns"]:
            types.setdefault(t, []).append(c)
    return {
        "setup_notebook": f"notebooks/{NOTEBOOK}",
        "setup_repo": SOURCE_REPO,
        "setup_branch": SOURCE_BRANCH,
        "setup_folder": SOURCE_FOLDER,
        "setup_files_source": LAKEHOUSE_FILES_SOURCE,
        "setup_file_count": len(m["files"]),
        "setup_mb": f"{sum(f['bytes'] for f in m['files'].values()) / 1e6:.0f}",
        "setup_lh_tables": len(lh),
        "setup_lh_rows": f"{sum(t['rows'] for t in lh.values()):,}",
        "setup_pack_rows": f"{lh['pack']['rows']:,}",
        "setup_case_rows": f"{lh['shipping_case']['rows']:,}",
        "setup_te_rows": f"{eh['TraceEvent']['rows']:,}",
        "setup_tel_rows": f"{eh['LineScannerTelemetry']['rows']:,}",
        "setup_types": _type_summary(types),
    }


def _type_summary(types):
    """One sentence on the lakehouse column types, for the tutorial page."""
    def cols(t, n=None):
        names = sorted(set(types.get(t, [])), key=lambda c: (not c.endswith("_ts"), c))
        shown = [f"`{c}`" for c in names[:n]]
        return (", ".join(shown[:-1]) + " and " + shown[-1] if len(shown) > 1 else "".join(shown)), len(names)
    parts = ["identifiers and texts are strings", "counts are integers"]
    text, n = cols("double", 3)
    if n:
        parts.append(f"{text} {'is a decimal number' if n == 1 else 'are decimal numbers'}")
    text, n = cols("boolean")
    if n:
        parts.append(f"{text} {'is a boolean' if n == 1 else 'are booleans'}")
    text, n = cols("timestamp", 3)
    if n:
        parts.append(f"times such as {text} are timestamps (UTC)")
    text, n = cols("date")
    if n:
        parts.append(f"{text} {'is a date' if n == 1 else 'are dates'}")
    return ", ".join(parts[:-1]) + ", and " + parts[-1]
