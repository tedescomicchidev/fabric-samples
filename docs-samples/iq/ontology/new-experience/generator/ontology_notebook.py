"""Writes notebooks/create_ontology.ipynb: creates the ontology of tutorial parts 1 and 2 in one run.

The notebook embeds the spec from ontology_spec.py and sends it to the Fabric REST API as an ontology
(preview) definition in the new-experience (TMDL) format:
https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/ontology-definition
"""
from __future__ import annotations

import json
import os

import ontology_spec

NB_INTRO = """# Create the TrackTraceOntology ontology (shortcut for tutorial parts 1 and 2)

This notebook creates the ontology (preview) item **TrackTraceOntology** in the current workspace with the result of
tutorial parts 1 and 2, so you can go straight to part 3. Like the semantic model notebook, it uses the Fabric REST
API; here it sends an ontology definition in the new-experience (TMDL) format.

**What it creates**

- The entity types bound to the **TrackTraceLH** lakehouse tables, with the property names, entity type keys,
  descriptions, synonyms and additional metadata from parts 1 and 2.
- The inherited entity types **Hub**, **Distributor**, **Cigarette** and **Heated Tobacco Stick**, if your
  tenant accepts entity type inheritance through the API. If not, the notebook skips them and says so.
- The relationship types between those entity types, bound with the mapping tables from part 1, with their
  descriptions.
- The six business rules from part 2.

**What it doesn't create**

**Trace Event**, **Scanner Telemetry** (eventhouse) and **Line Production Day** (semantic model), and the
relationship types that use them. The definition format for those bindings isn't documented yet. The last cell
lists the steps to add them in the ontology editor, which takes about 10 minutes. The tutorial page
`tutorial/tutorial-1-2-shortcut.md` describes the same steps.

**Run**

1. Complete part 0: the lakehouse **TrackTraceLH** with its 18 tables, the eventhouse and the semantic model.
1. Import this notebook into the tutorial workspace and select **Run all**. It runs on the Python or the PySpark
   kernel and doesn't need a default lakehouse.
1. Read the output of the last cell and finish the ontology as described there.

If **TrackTraceOntology** already exists and has entity types, the notebook stops without changing it. Set
`REPLACE_EXISTING = True` in the next cell to replace its whole definition; changes you made in the editor are
lost.

> Ontology is in preview. This notebook follows the documented definition format as of November 2026; parts of it
> are marked as untested in the code. If the service rejects the definition, the notebook prints the service's
> error message.
"""

NB_SETTINGS = r'''# Settings. The defaults match the tutorial.
ONTOLOGY_NAME = "TrackTraceOntology"
LAKEHOUSE_NAME = "TrackTraceLH"
LAKEHOUSE_SCHEMA = "dbo"
INCLUDE_OPTIONAL_RELATIONSHIPS = True  # the "Extra context (optional)" relationship types of part 1
INCLUDE_INHERITED_TYPES = True         # Hub, Distributor, Cigarette, Heated Tobacco Stick
RELATIONSHIP_BINDING = "auto"          # "mapping_table", "direct", or "auto" (mapping tables, else direct)
REPLACE_EXISTING = False               # True replaces the whole definition of an existing ontology
SHOW_TMDL = False                      # True prints every definition part before it's sent
'''

NB_CONNECT = r'''# Find the lakehouse and its SQL analytics endpoint, and read the column types of its tables.
import base64, json, re, time, uuid
import sempy.fabric as fabric

WORKSPACE_ID = fabric.get_workspace_id()
client = fabric.FabricRestClient()


def call(method, url, what, **kwargs):
    r = getattr(client, method)(url, **kwargs)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"{what} failed: HTTP {r.status_code} {r.text[:2000]}")
    return r


def wait(r, what):
    """Wait for a long-running operation. Returns (True, result) or (False, error text)."""
    if r.status_code in (200, 201):
        return True, (r.json() if r.text else {})
    op_id = r.headers.get("x-ms-operation-id")
    if not op_id:
        return False, f"{what}: HTTP {r.status_code} without an operation ID"
    for _ in range(180):
        time.sleep(min(int(r.headers.get("Retry-After") or 5), 10))
        st = client.get(f"v1/operations/{op_id}").json()
        if st.get("status") == "Succeeded":
            res = client.get(f"v1/operations/{op_id}/result")
            return True, (res.json() if res.status_code == 200 and res.text else {})
        if st.get("status") in ("Failed", "Cancelled"):
            return False, json.dumps(st.get("error") or st, indent=1)
    return False, f"{what} didn't finish within 30 minutes"


def list_items(kind):
    items, token = [], None
    while True:
        url = f"v1/workspaces/{WORKSPACE_ID}/{kind}" + (f"?continuationToken={token}" if token else "")
        body = call("get", url, f"List {kind}").json()
        items += body.get("value", [])
        token = body.get("continuationToken")
        if not token:
            return items


lakehouse = next((i for i in list_items("lakehouses") if i["displayName"] == LAKEHOUSE_NAME), None)
if lakehouse is None:
    raise RuntimeError(f"No lakehouse named {LAKEHOUSE_NAME} in this workspace. Complete part 0 of the tutorial first.")
LAKEHOUSE_ID = lakehouse["id"]
lh_props = call("get", f"v1/workspaces/{WORKSPACE_ID}/lakehouses/{LAKEHOUSE_ID}", "Get lakehouse").json()
sql = (lh_props.get("properties") or {}).get("sqlEndpointProperties") or {}
SQL_HOST, SQL_ENDPOINT_ID = sql.get("connectionString"), sql.get("id")
if not (SQL_HOST and SQL_ENDPOINT_ID):
    raise RuntimeError(f"The SQL analytics endpoint of {LAKEHOUSE_NAME} isn't ready "
                       f"(status: {sql.get('provisioningStatus')}). Wait a minute and run the notebook again.")

# Delta column types -> TMDL data types. Columns of other types (binary, arrays, ...) are left out.
TYPE_MAP = {"string": "string", "varchar": "string", "char": "string",
            "bigint": "int64", "long": "int64", "int": "int64", "integer": "int64", "smallint": "int64",
            "short": "int64", "tinyint": "int64", "byte": "int64",
            "double": "double", "float": "double", "real": "double",
            "boolean": "boolean", "bool": "boolean",
            "timestamp": "dateTime", "timestamp_ntz": "dateTime", "date": "dateTime"}


def tmdl_type(delta_type):
    t = str(delta_type).lower()
    return "decimal" if t.startswith("decimal") else TYPE_MAP.get(t)


def spark_available():
    try:
        spark  # noqa: F821  (defined in PySpark notebooks)
        return True
    except NameError:
        return False


def read_columns(table):
    path = (f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/Tables/"
            f"{LAKEHOUSE_SCHEMA}/{table}")
    if spark_available():
        fields = [(f.name, f.dataType.simpleString()) for f in spark.read.format("delta").load(path).schema.fields]  # noqa: F821
    else:  # Python notebook
        import notebookutils
        from deltalake import DeltaTable
        dt = DeltaTable(path, storage_options={"bearer_token": notebookutils.credentials.getToken("storage"),
                                               "use_fabric_endpoint": "true"})
        fields = [(f.name, getattr(f.type, "type", f.type)) for f in dt.schema().fields]
    return [(name, tmdl_type(t), str(t)) for name, t in fields]


needed = sorted({e["table"] for e in SPEC["entity_types"] if e["source"] == "lakehouse"} |
                {r["mapping_table"] for r in SPEC["relationship_types"] if r["source"] == "lakehouse"})
COLUMNS, missing, left_out = {}, [], []
for table in needed:
    try:
        cols = read_columns(table)
    except Exception as e:  # table not found or not readable
        missing.append(f"{table} ({type(e).__name__})")
        continue
    left_out += [f"{table}.{c} ({t})" for c, typ, t in cols if typ is None]
    COLUMNS[table] = {c: typ for c, typ, _ in cols if typ}
if missing:
    raise RuntimeError(f"These tables aren't readable in {LAKEHOUSE_NAME}/{LAKEHOUSE_SCHEMA}: {', '.join(missing)}. "
                       "Load them as described in part 0, 'Prepare the lakehouse'.")
print(f"Lakehouse {LAKEHOUSE_NAME}: read the columns of {len(COLUMNS)} tables "
      f"({'Spark' if spark_available() else 'deltalake'}). SQL analytics endpoint: {SQL_HOST}")
if left_out:
    print("Left out (unsupported column types):", ", ".join(left_out))
'''

NB_BUILD = r'''# Build the ontology definition (TMDL parts) from SPEC and the lakehouse columns.
T = "\t"
SIMPLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
ENTITIES = {e["name"]: e for e in SPEC["entity_types"]}
warnings = []


def q(name):
    """TMDL name: single-quoted when it has spaces or special characters."""
    return name if SIMPLE_NAME.match(name) else "'" + name.replace("'", "''") + "'"


def col_ref(table, column):
    return f"{q(table)}.{q(column)}"


def tag(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "tracktrace-ontology/" + "/".join(parts)))


def doc(text, indent=""):
    return [f"{indent}/// {line}" for line in text.splitlines()] if text else []


def table_tmdl(name, source_table, columns):
    lines = [f"table {q(name)}", f"{T}lineageTag: {tag('table', name)}", ""]
    for col, typ in columns.items():
        lines += [f"{T}column {q(col)}", f"{T*2}dataType: {typ}", f"{T*2}lineageTag: {tag('column', name, col)}",
                  f"{T*2}sourceColumn: {col}", ""]
    lines += [f"{T}partition {q(name)} = entity", f"{T*2}mode: directLake", f"{T*2}source",
              f"{T*3}entityName: {source_table}", f"{T*3}schemaName: {LAKEHOUSE_SCHEMA}",
              f"{T*3}expressionSource: DatabaseQuery", ""]
    return "\n".join(lines) + "\n"


def entity_tmdl(e, table, variant=None):
    """variant (inherited entity types only): {"redefines": "block" | "json", "metadata": bool}"""
    base = ENTITIES[e["base"]] if e["base"] else None
    renames = (base or e)["renames"]
    with_metadata = variant is None or variant["metadata"]
    lines = doc(e["description"]) if with_metadata else []
    lines += [f"entity {q(e['name'])}", f"{T}lineageTag: {tag('entity', e['name'])}"]
    if base:
        lines.append(f"{T}baseEntityType: {q(base['name'])}")
    lines.append(f"{T}backingTable: {q(table)}")
    if e["key"] and with_metadata:
        lines.append(f"{T}keyProperty: {q(e['key'])}")
    if with_metadata:
        lines += [f"{T}synonym {q(s)}" for s in e["synonyms"]]
    lines.append("")
    for col, typ in COLUMNS[e["table"]].items():
        prop = renames.get(col, col)
        if not base:
            lines += doc(e["property_descriptions"].get(prop), T)
        lines += [f"{T}property {q(prop)}", f"{T*2}dataType: {typ}",
                  f"{T*2}lineageTag: {tag('property', e['name'], prop)}", ""]
        if base and variant["redefines"] == "block":  # untested: no documented example of redefines
            lines += [f"{T*2}redefines", f"{T*3}entity: {q(base['name'])}", f"{T*3}property: {q(prop)}", ""]
        elif base:
            lines += [f"{T*2}redefines = " + json.dumps({"entity": base["name"], "property": prop}), ""]
        lines += [f"{T*2}backingConfiguration", f"{T*3}valueColumn: {col_ref(table, col)}", ""]
    if with_metadata:
        lines += [f"{T}annotation {q(k)} = {v}" for k, v in e["annotations"]]
    return "\n".join(lines).rstrip("\n") + "\n\n"


def creates_ambiguity(edges, new):
    """True if the active relationship `new` (from_table, to_table) adds a second path between two tables."""
    def reach(a):
        seen, todo = set(), [a]
        while todo:
            for b in edges.get(todo.pop(), ()):
                if b not in seen:
                    seen.add(b)
                    todo.append(b)
        return seen
    u, v = new
    if u == v or v in edges.get(u, ()):
        return True
    ancestors = {u} | {a for a in list(edges) if u in reach(a)}
    descendants = {v} | reach(v)
    return any(d in reach(a) for a in ancestors for d in descendants)


def relationship_tmdl(mode, relationships):
    """Returns (extra tables, relationships.tmdl lines, entityRelationships.tmdl lines, created names)."""
    tables, tom, er, created, active = {}, [], [], [], {}
    for r in relationships:
        o, t = ENTITIES[r["origin"]], ENTITIES[r["target"]]
        c1, c2 = r["mapping_columns"]
        mcols = COLUMNS[r["mapping_table"]]
        if mcols.get(c1) != COLUMNS[o["table"]].get(o["key"]) or mcols.get(c2) != COLUMNS[t["table"]].get(t["key"]):
            warnings.append(f"Skipped relationship type {r['name']}: the column types of {r['mapping_table']} "
                            f"don't match the keys of {o['name']} and {t['name']}.")
            continue
        if mode == "mapping_table":
            # The mapping table gets its own TOM table: the same lakehouse table can't be both an entity type's
            # backing table and a relationship's mapping table.
            mt = f"map_{r['name']}"
            tables[mt] = table_tmdl(mt, r["mapping_table"], {c1: mcols[c1], c2: mcols[c2]})
            tom += [f"relationship {q(mt + '_from')}", f"{T}fromColumn: {col_ref(mt, c1)}",
                    f"{T}toColumn: {col_ref(o['table'], o['key'])}", "",
                    f"relationship {q(mt + '_to')}", f"{T}fromColumn: {col_ref(mt, c2)}",
                    f"{T}toColumn: {col_ref(t['table'], t['key'])}", ""]
            backing = [f"{T*2}type: table", f"{T*2}table: {q(mt)}", f"{T*2}fromRelationship: {q(mt + '_from')}",
                       f"{T*2}toRelationship: {q(mt + '_to')}"]
        else:
            # Direct: one TOM relationship from the foreign key column to the key of the other entity type.
            if r["mapping_table"] == o["table"]:
                frm, to = col_ref(o["table"], c2), col_ref(t["table"], t["key"])
                edge = (o["table"], t["table"])
            else:
                frm, to = col_ref(t["table"], c1), col_ref(o["table"], o["key"])
                edge = (t["table"], o["table"])
            name = f"rel_{r['name']}"
            tom += [f"relationship {q(name)}", f"{T}fromColumn: {frm}", f"{T}toColumn: {to}"]
            if creates_ambiguity(active, edge):  # a second active path between two tables isn't allowed
                tom.append(f"{T}isActive: false")
            else:
                active.setdefault(edge[0], set()).add(edge[1])
            tom.append("")
            backing = [f"{T*2}relationship: {q(name)}"]
        er += doc(r["description"]) + [
            f"entityRelationship {q(r['name'])}", f"{T}lineageTag: {tag('relationship', r['name'])}",
            f"{T}fromEntity: {q(r['origin'])}", f"{T}toEntity: {q(r['target'])}", "",
            f"{T}backingConfiguration"] + backing + [""]
        created.append(r["name"])
    return tables, tom, er, created


def rule_tmdl(rule, entity_names):
    lines = [f"rule {q(rule['name'])}", f"{T}statement: {rule['statement']}",
             f"{T}lineageTag: {tag('rule', rule['name'])}", ""]
    for name in rule["entities"]:
        if name in entity_names:
            lines += [f"{T}ruleReferencedEntity {q(name)}", ""]
    return "\n".join(lines) + "\n"


def build_definition(mode, inherited_variant=None):
    """Returns ({path: text}, summary). mode: "mapping_table" or "direct"."""
    warnings.clear()
    base_types = [e for e in SPEC["entity_types"] if e["source"] == "lakehouse" and not e["base"]]
    derived = [e for e in SPEC["entity_types"] if e["source"] == "lakehouse" and e["base"]]
    tables = {e["table"]: table_tmdl(e["table"], e["table"], COLUMNS[e["table"]]) for e in base_types}
    entities = {e["name"]: entity_tmdl(e, e["table"]) for e in base_types}
    if inherited_variant:
        for e in derived:  # own TOM table, because a TOM table can back only one entity type
            own = f"{e['table']}_{re.sub(r'[^a-z0-9]+', '_', e['name'].lower())}"
            tables[own] = table_tmdl(own, e["table"], COLUMNS[e["table"]])
            entities[e["name"]] = entity_tmdl(e, own, inherited_variant)
    rels = [r for r in SPEC["relationship_types"] if r["source"] == "lakehouse"
            and (INCLUDE_OPTIONAL_RELATIONSHIPS or not r["optional"])]
    extra_tables, tom, er, created = relationship_tmdl(mode, rels)
    tables.update(extra_tables)
    rules = {r["name"]: rule_tmdl(r, entities) for r in SPEC["rules"]}
    expression = "\n".join([
        "expression DatabaseQuery =", f"{T*2}let",
        f'{T*2}    database = Sql.Database("{SQL_HOST}", "{SQL_ENDPOINT_ID}")', f"{T*2}in", f"{T*2}    database",
        f"{T}lineageTag: {tag('expression', 'DatabaseQuery')}", ""]) + "\n"
    model = "\n".join(["model Model", ""] + [f"ref table {q(t)}" for t in tables] + [""] +
                      [f"ref entity {q(e)}" for e in entities] + ["", "ref namespace default", ""] +
                      [f"ref rule {q(r)}" for r in rules]) + "\n"
    parts = {"database.tmdl": f"database\n{T}compatibilityLevel: 1000000\n",
             "model.tmdl": model,
             "namespaces/default.tmdl": f"namespace default\n{T}lineageTag: default\n",
             "expressions.tmdl": expression,
             "relationships.tmdl": "\n".join(tom) + "\n",
             "entityRelationships.tmdl": "\n".join(er) + "\n"}
    parts.update({f"tables/{name}.tmdl": text for name, text in tables.items()})
    parts.update({f"entities/{name}.tmdl": text for name, text in entities.items()})
    parts.update({f"rules/{name}.tmdl": text for name, text in rules.items()})
    summary = {"entity types": list(entities), "relationship types": created, "rules": list(rules),
               "tables": len(tables), "warnings": list(warnings)}
    return parts, summary


core_parts, core_summary = build_definition("mapping_table")
print(f"Definition ready: {len(core_summary['entity types'])} entity types, "
      f"{len(core_summary['relationship types'])} relationship types, {len(core_summary['rules'])} rules, "
      f"{core_summary['tables']} backing tables, {len(core_parts)} parts.")
for w in core_summary["warnings"]:
    print("Warning:", w)
if SHOW_TMDL:
    for path, text in core_parts.items():
        print(f"----- {path}\n{text}")
'''

NB_DEPLOY = r'''# Create the ontology item, or reuse an existing empty one, and send the definition.
def b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def get_definition(ontology_id):
    r = call("post", f"v1/workspaces/{WORKSPACE_ID}/ontologies/{ontology_id}/getDefinition", "Get definition")
    ok, res = wait(r, "Get definition")
    if not ok:
        raise RuntimeError(f"Get definition failed: {res}")
    return {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in res["definition"]["parts"]}


def apply(parts, what):
    body = {"definition": {"parts": [{"path": p, "payload": b64(t), "payloadType": "InlineBase64"}
                                     for p, t in parts.items()]}}
    r = client.post(f"v1/workspaces/{WORKSPACE_ID}/ontologies/{ONTOLOGY_ID}/updateDefinition", json=body)
    if r.status_code not in (200, 201, 202):
        return False, f"HTTP {r.status_code} {r.text[:3000]}"
    return wait(r, what)


ontology = next((o for o in list_items("ontologies") if o["displayName"] == ONTOLOGY_NAME), None)
if ontology:
    ONTOLOGY_ID = ontology["id"]
    info = call("get", f"v1/workspaces/{WORKSPACE_ID}/ontologies/{ONTOLOGY_ID}", "Get ontology").json()
    if (info.get("properties") or {}).get("generation") == 1:
        raise RuntimeError(f"{ONTOLOGY_NAME} was created with the old ontology experience. Delete or rename it, "
                           "and run the notebook again.")
    existing = [p for p in get_definition(ONTOLOGY_ID) if p.startswith("entities/")]
    if existing and not REPLACE_EXISTING:
        raise RuntimeError(f"{ONTOLOGY_NAME} already has {len(existing)} entity types, so the notebook didn't change "
                           "it. Set REPLACE_EXISTING = True to replace its definition, or delete it first.")
    print(f"Using the existing ontology {ONTOLOGY_NAME} ({ONTOLOGY_ID}).")
else:
    r = call("post", f"v1/workspaces/{WORKSPACE_ID}/ontologies", "Create ontology",
             json={"displayName": ONTOLOGY_NAME,
                   "description": "Track & Trace demo ontology (synthetic data), created by create_ontology.ipynb."})
    ok, res = wait(r, "Create ontology")
    if not ok:
        raise RuntimeError(f"Create ontology failed: {res}")
    ONTOLOGY_ID = None
    for _ in range(10):  # the new item can take a moment to show up in the list
        ONTOLOGY_ID = next((o["id"] for o in list_items("ontologies") if o["displayName"] == ONTOLOGY_NAME), None)
        if ONTOLOGY_ID:
            break
        time.sleep(3)
    if not ONTOLOGY_ID:
        raise RuntimeError(f"Created {ONTOLOGY_NAME}, but it isn't listed yet. Run the notebook again in a minute.")
    print(f"Created the ontology {ONTOLOGY_NAME} ({ONTOLOGY_ID}).")

# 1. Entity types, relationship types and rules. With RELATIONSHIP_BINDING = "auto", mapping tables are tried
#    first (needed for the graph in part 3), then direct column-to-key bindings.
modes = ["mapping_table", "direct"] if RELATIONSHIP_BINDING == "auto" else [RELATIONSHIP_BINDING]
APPLIED_MODE, errors = None, {}
for mode in modes:
    parts, summary = build_definition(mode)
    print(f"Sending the definition with {mode.replace('_', ' ')} relationship bindings ...")
    ok, err = apply(parts, "Update definition")
    if ok:
        APPLIED_MODE, APPLIED_SUMMARY = mode, summary
        print("  Accepted.")
        break
    errors[mode] = err
    print(f"  Not accepted:\n{err[:3000]}")
if APPLIED_MODE is None:
    raise RuntimeError("The service didn't accept the ontology definition. The errors are printed above. "
                       "Follow tutorial parts 1 and 2 to build the ontology in the editor instead.")

# 2. Inherited entity types (preview, rolling out). Untested: the definition format of an inherited
#    property's binding isn't documented with an example, so two spellings are tried.
INHERITED_OK, inherited_error = None, None
if INCLUDE_INHERITED_TYPES:
    for variant in ({"redefines": "block", "metadata": True}, {"redefines": "json", "metadata": True},
                    {"redefines": "block", "metadata": False}, {"redefines": "json", "metadata": False}):
        parts, summary = build_definition(APPLIED_MODE, variant)
        ok, err = apply(parts, "Update definition (inherited entity types)")
        if ok:
            INHERITED_OK, APPLIED_SUMMARY = variant, summary
            break
        inherited_error = err
    if INHERITED_OK:
        print("Added the inherited entity types" +
              ("." if INHERITED_OK["metadata"] else " without their descriptions; add them as in part 2."))
    else:
        print("The inherited entity types weren't accepted, so the ontology has none. Last error:\n"
              f"{(inherited_error or '')[:2000]}")
'''

NB_VERIFY = r'''# Check what the ontology contains now, and list the steps that are left.
current = get_definition(ONTOLOGY_ID)
have_entities = sorted(p[len("entities/"):-len(".tmdl")] for p in current if p.startswith("entities/"))
have_rels = re.findall(r"^entityRelationship (.+)$", current.get("entityRelationships.tmdl", ""), re.M)
have_rules = [p for p in current if p.startswith("rules/")]
print(f"{ONTOLOGY_NAME} has {len(have_entities)} entity types, {len(have_rels)} relationship types and "
      f"{len(have_rules)} rules. Relationship bindings: {APPLIED_MODE.replace('_', ' ')}.")
print("Entity types:", ", ".join(have_entities))

steps = []
by_source = lambda s: [e for e in SPEC["entity_types"] if e["source"] == s]
for e in by_source("eventhouse"):
    text = (f"Add the entity type '{e['name']}': + Add > Entity type, then Bind data > OneLake catalog > "
            f"{SPEC['eventhouse']} > {e['table']}, and keep all columns as properties.")
    if e["description"]:
        text += f"\n     Description: {e['description']}"
    if e["synonyms"]:
        text += f"\n     Synonyms: {', '.join(e['synonyms'])}"
    for prop, d in e["property_descriptions"].items():
        text += f"\n     Property {prop}: {d}"
    steps.append(text)
for e in by_source("semantic_model"):
    steps.append(f"Add '{e['name']}' with the ontology agent. In Plan mode, send: \"Create a new entity type called "
                 f"{e['name']}, bound to data in the {e['table']} table from the {SPEC['semantic_model']} semantic "
                 "model inside this workspace.\" Then switch to Act mode and send \"Apply the entity type plan\". "
                 "Check that it has the three metrics.")
for r in SPEC["relationship_types"]:
    if r["source"] != "lakehouse" and (INCLUDE_OPTIONAL_RELATIONSHIPS or not r["optional"]):
        text = (f"Add the relationship type '{r['name']}': {r['origin']} ({r['origin_property']}) -> "
                f"{r['target']} ({r['target_property']}), without a mapping table"
                + (" (optional)." if r["optional"] else "."))
        if r["description"]:
            text += f"\n     Description: {r['description']}"
        steps.append(text)
for rule in SPEC["rules"]:
    later = [x for x in rule["entities"] if ENTITIES[x]["source"] != "lakehouse"]
    if later:
        steps.append(f"Open the rule '{rule['name']}' and add {', '.join(later)} to its linked ontology elements.")
if INCLUDE_INHERITED_TYPES and not INHERITED_OK:
    steps.append("Optional: add Hub and Distributor (inherit from Warehouse, table warehouse) and Cigarette and "
                 "Heated Tobacco Stick (inherit from Product, table product) as in part 1, with the descriptions "
                 "from part 2.")
elif INHERITED_OK and not INHERITED_OK["metadata"]:
    steps.append("Add the descriptions of Hub, Distributor, Cigarette and Heated Tobacco Stick from part 2.")
if APPLIED_MODE == "direct":
    steps.append("For the graph in part 3, open the relationship types you want to project and turn on "
                 "'Use mapping table' with the table from part 1.")

print("\nFinish the ontology in the editor, then continue with tutorial part 3 (Explore the ontology):")
for i, s in enumerate(steps, 1):
    print(f"{i:>2}. {s}")
print("\nThe entity type keys are already set, so in part 3 'Prepare the graph' is only a check.")
'''


def _md_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _code_cell(text):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": text.splitlines(keepends=True)}


def spec_cell():
    spec = json.dumps(ontology_spec.notebook_spec(), indent=1, ensure_ascii=False)
    return ("# The ontology of tutorial parts 1 and 2: entity types, relationship types and rules.\n"
            "# Generated from generator/ontology_spec.py; the texts are the ones in the tutorial.\n"
            "import json\n\n"
            f'SPEC = json.loads(r"""\n{spec}\n""")\n')


def write_notebook(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nb = {
        "cells": [
            _md_cell(NB_INTRO),
            _code_cell(NB_SETTINGS),
            _code_cell(spec_cell()),
            _code_cell(NB_CONNECT),
            _code_cell(NB_BUILD),
            _code_cell(NB_DEPLOY),
            _code_cell(NB_VERIFY),
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
