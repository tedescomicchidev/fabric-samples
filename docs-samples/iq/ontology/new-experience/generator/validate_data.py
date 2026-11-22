#!/usr/bin/env python3
"""Check the generated Track & Trace data set: seeded scenarios S1-S6 and the data-quality rules.

Usage:
    python validate_data.py                 # validates the parent folder (new-experience/)
    python validate_data.py --data /tmp/tt-demo

Reads only the CSV files, so it validates exactly what you upload to Fabric. Exits with code 1
if any check fails.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def load(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_parts(folder):
    rows = []
    for p in sorted(glob.glob(os.path.join(folder, "part-*.csv"))):
        rows.extend(load(p))
    return rows


def t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) if s else None


class Checker:
    def __init__(self):
        self.failures = 0

    def check(self, name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        if not ok:
            self.failures += 1


def _norm(text):
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def _complete(text, page):
    """The whole text is in the page: it ends where a table cell, a synonym list or a step ends."""
    return re.search(re.escape(_norm(text)) + r"(?= \|| Synonyms:| 1\. Select| Low days of cover :)", page) is not None


def check_ontology(c, data, tdir):
    """ontology_spec.py (embedded in notebooks/create_ontology.ipynb) against the CSV files and the tutorial."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ontology_spec as spec

    def header(table):
        path = os.path.join(data, "lakehouse", f"{table}.csv")
        if not os.path.exists(path):
            path = sorted(glob.glob(os.path.join(data, "lakehouse", table, "part-*.csv")))[0]
        with open(path, encoding="utf-8") as fh:
            return next(csv.reader(fh))

    def page(name):
        path = os.path.join(tdir, name)
        return open(path, encoding="utf-8").read() if os.path.exists(path) else ""

    p1, p2 = _norm(page("tutorial-1-create-ontology.md")), _norm(page("tutorial-2-enrich-ontology.md"))
    p3 = page("tutorial-3-explore-ontology.md")
    ents = {e["name"]: e for e in spec.ENTITY_TYPES}
    bad_cols, bad_docs = [], []
    for e in spec.ENTITY_TYPES:
        if e["source"] == "lakehouse":
            cols = header(e["table"])
            renames = (ents[e["base"]] if e["base"] else e)["renames"]
            props = [renames.get(x, x) for x in cols]
            bad_cols += [f"{e['name']}.{x}" for x in list(e["renames"]) + [e["key"]] + list(e["property_descriptions"])
                         if x not in (cols if x in e["renames"] else props)]
            if e["base"]:
                row = f"| {e['name']} | {e['base']} | TrackTraceLH > {e['table']} | (inherited) |"
            else:
                ren = ", ".join(f"{k} → {v}" for k, v in e["renames"].items())
                row = _norm(f"| {e['name']} | | TrackTraceLH > {e['table']} | {ren} |")
            if e["name"] not in ("Warehouse", "Distributor") and row not in p1:
                bad_docs.append(f"part 1 row of {e['name']}")
        elif e["source"] == "eventhouse" and f"| {e['name']} | | TrackTraceEH > {e['table']} |" not in p1:
            bad_docs.append(f"part 1 row of {e['name']}")
        texts = [e["description"]] + list(e["property_descriptions"].values())
        texts += [f"{k} : {v}" for k, v in e["annotations"]]
        texts += ["Synonyms: " + ", ".join(e["synonyms"])] if e["synonyms"] else []
        bad_docs += [f"part 2 metadata of {e['name']}: {x[:40]}" for x in texts if x and not _complete(x, p2)]
        if e["key"] and not any(
                len(cells) == 2 and e["name"] in [x.strip() for x in cells[0].split(",")] and cells[1] == e["key"]
                for cells in ([x.strip() for x in line.strip().strip("|").split("|")] for line in p3.splitlines())):
            bad_docs.append(f"part 3 key of {e['name']}")
    for r in spec.RELATIONSHIP_TYPES:
        if r["mapping_table"]:
            bad_cols += [f"{r['name']}: {r['mapping_table']}.{x}" for x in r["mapping_columns"]
                         if x not in header(r["mapping_table"])]
            for side, col in ((r["origin"], r["mapping_columns"][0]), (r["target"], r["mapping_columns"][1])):
                if ents[side]["source"] != "lakehouse" or not ents[side]["key"]:
                    bad_cols.append(f"{r['name']}: {side} has no lakehouse key for {col}")
            mapping = f"{r['mapping_table']} ({', '.join(r['mapping_columns'])})"
        else:
            mapping = r["mapping_text"]
        row = f"| {r['name']} | {r['origin']} ({r['origin_property']}) | {r['target']} ({r['target_property']}) | {mapping} |"
        if row not in p1:
            bad_docs.append(f"part 1 row of {r['name']}")
        if r["description"] and not _complete(r["description"], p2):
            bad_docs.append(f"part 2 description of {r['name']}")
    for i, rule in enumerate(spec.RULES):
        want = ([f"{_norm(rule['statement'])} - Linked ontology elements: " + ", ".join(rule["entities"])] if i == 0 else
                [f"| {rule['name']} | {_norm(rule['statement'])} | {', '.join(rule['entities'])} |"])
        bad_docs += [f"part 2 rule {rule['name']}" for w in want if w not in p2]
        bad_docs += [f"rule {rule['name']}: unknown entity type {x}" for x in rule["entities"] if x not in ents]
    c.check("Ontology spec: columns, keys and mapping tables exist in the CSV files", not bad_cols,
            ", ".join(bad_cols[:5]))
    c.check("Ontology spec: matches the tutorial (parts 1 to 3)", not bad_docs, ", ".join(bad_docs[:5]))

    nb_path = os.path.join(data, "notebooks", "create_ontology.ipynb")
    ok, detail = os.path.exists(nb_path), "missing"
    if ok:
        nb = json.load(open(nb_path, encoding="utf-8"))
        code = ["".join(x["source"]) for x in nb["cells"] if x["cell_type"] == "code"]
        try:
            for src in code:
                compile(src, "create_ontology.ipynb", "exec")
            embedded = json.loads(re.search(r'SPEC = json.loads\(r"""\n(.*)\n"""\)', "\n".join(code), re.S).group(1))
            ok = embedded == json.loads(json.dumps(spec.notebook_spec()))
            detail = "" if ok else "embedded spec differs from ontology_spec.py"
        except (SyntaxError, AttributeError) as e:
            ok, detail = False, str(e)
    c.check("Notebook create_ontology.ipynb: compiles and embeds the current ontology spec", ok, detail)


def check_setup(c, data):
    """notebooks/setup_workspace.ipynb against the data files, ontology_spec.py and the generator."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ontology_spec as spec
    import setup_notebook as sn

    path = os.path.join(data, "notebooks", sn.NOTEBOOK)
    if not os.path.exists(path):
        c.check(f"Notebook {sn.NOTEBOOK}: exists", False, "missing")
        return
    text = open(path, encoding="utf-8").read()
    code = ["".join(x["source"]) for x in json.loads(text)["cells"] if x["cell_type"] == "code"]
    expected = sn.build_manifest(data)
    ok, detail = True, ""
    try:
        for src in code:
            compile(src, sn.NOTEBOOK, "exec")
        embedded = json.loads(re.search(r'MANIFEST = json.loads\(r"""\n(.*?)\n"""\)', "\n".join(code), re.S).group(1))
        if embedded != expected:
            ok, detail = False, "the embedded manifest differs from the data files"
    except (SyntaxError, AttributeError) as e:
        ok, detail = False, str(e)
    c.check(f"Notebook {sn.NOTEBOOK}: compiles, and its manifest matches the data files (checksums, rows, columns)",
            ok, detail)
    current = text == sn.notebook_text(data)
    c.check(f"Notebook {sn.NOTEBOOK}: up to date with the generator (settings, reused cells, ontology spec)",
            current, "" if current else "run generate_data.py again")

    # Keys and mapping columns must load as strings, so that the relationship types of the ontology bind.
    types = {t: dict(v["columns"]) for t, v in expected["lakehouse_tables"].items()}
    bad = [f"{e['table']}.{e['key']}" for e in spec.ENTITY_TYPES
           if e["source"] == "lakehouse" and e["key"] and types[e["table"]].get(e["key"]) != "string"]
    bad += [f"{r['mapping_table']}.{x}" for r in spec.RELATIONSHIP_TYPES if r["mapping_table"]
            for x in r["mapping_columns"] if types[r["mapping_table"]].get(x) != "string"]
    c.check(f"Notebook {sn.NOTEBOOK}: entity type keys and mapping columns load as strings", not bad,
            ", ".join(bad[:5]))
    missing = [t for t in sorted({e["table"] for e in spec.ENTITY_TYPES if e["source"] == "eventhouse"})
               if t not in expected["eventhouse_tables"]]
    c.check(f"Notebook {sn.NOTEBOOK}: loads the eventhouse tables of the ontology", not missing, ", ".join(missing))


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--data", default=os.path.dirname(here))
    args = ap.parse_args()
    lh = os.path.join(args.data, "lakehouse")
    eh = os.path.join(args.data, "eventhouse")
    c = Checker()

    product = {r["sku"]: r for r in load(f"{lh}/product.csv")}
    warehouse = {r["warehouse_id"]: r for r in load(f"{lh}/warehouse.csv")}
    lines = {r["line_id"]: r for r in load(f"{lh}/production_line.csv")}
    orders = {r["order_id"]: r for r in load(f"{lh}/production_order.csv")}
    packs = load_parts(f"{lh}/pack")
    bundles = load(f"{lh}/bundle.csv")
    cases = load(f"{lh}/shipping_case.csv")
    pallets = load(f"{lh}/pallet.csv")
    shipments = {r["shipment_id"]: r for r in load(f"{lh}/shipment.csv")}
    subs = load(f"{lh}/authority_submission.csv")
    inv = load(f"{lh}/inventory_snapshot.csv")
    fc = load(f"{lh}/demand_forecast.csv")
    mnt = load(f"{lh}/maintenance_log.csv")
    scans = load(f"{lh}/consumer_scan.csv")
    events = load_parts(f"{eh}/trace_event")
    tel = load(f"{eh}/line_scanner_telemetry.csv")
    kpi = load(os.path.join(args.data, "semantic-model", "production_line_daily.csv"))

    as_of = max(t(r["snapshot_ts"]) for r in inv) + timedelta(hours=1)
    yday = (as_of - timedelta(days=1)).date().isoformat()
    print(f"Data snapshot (as-of): {as_of:%Y-%m-%d %H:%M} UTC; 'yesterday' = {yday}\n")

    bundle_by = {b["bundle_uid"]: b for b in bundles}
    case_by = {x["case_uid"]: x for x in cases}
    pallet_by = {p["pallet_uid"]: p for p in pallets}

    # ---------------- referential integrity
    c.check("unique pack UIDs", len({p["pack_uid"] for p in packs}) == len(packs))
    c.check("every pack references an existing order and SKU",
            all(p["order_id"] in orders and p["sku"] in product for p in packs))
    c.check("every bundle UID referenced by a pack exists",
            all(p["bundle_uid"] in bundle_by for p in packs if p["bundle_uid"]))
    c.check("every case referenced by a bundle exists", all(b["case_uid"] in case_by for b in bundles if b["case_uid"]))
    c.check("every case belongs to a pallet that exists", all(x["pallet_uid"] in pallet_by for x in cases))
    c.check("every pallet shipment exists", all(p["shipment_id"] in shipments for p in pallets if p["shipment_id"]))
    c.check("every shipment destination is a warehouse", all(s["to_location"] in warehouse for s in shipments.values()))
    c.check("every submission references a shipment", all(s["shipment_id"] in shipments for s in subs))

    # ---------------- data-quality rules
    no_bundle = [p for p in packs if not p["bundle_uid"]]
    c.check("every active pack belongs to exactly one bundle (only decommissioned packs have none)",
            all(p["status"] == "DECOMMISSIONED" for p in no_bundle), f"{len(no_bundle)} decommissioned packs")
    orphan_b = [b for b in bundles if not b["case_uid"]]
    c.check("bundles without a case exist only in S1 (status NOT_AGGREGATED)",
            all(b["status"] == "NOT_AGGREGATED" and b["line_id"] == "PL-02-L3" for b in orphan_b),
            f"{len(orphan_b)} bundles")
    bcount = Counter(b["case_uid"] for b in bundles if b["case_uid"])
    detail_cases = [x for x in cases if x["case_uid"] in bcount]
    c.check("bundle_count on each case equals its bundle rows (unit-level window)",
            all(int(x["bundle_count"]) == bcount[x["case_uid"]] for x in detail_cases), f"{len(detail_cases)} cases")
    pcount = Counter(p["bundle_uid"] for p in packs if p["bundle_uid"])
    c.check("every bundle holds pack_count packs", all(pcount[b["bundle_uid"]] == int(b["pack_count"]) for b in bundles))
    cpp = Counter(x["pallet_uid"] for x in cases)
    c.check("case_count on each pallet equals its case rows", all(cpp[p["pallet_uid"]] == int(p["case_count"]) for p in pallets))

    ev_by_obj = defaultdict(list)
    for e in events:
        ev_by_obj[e["object_uid"]].append(e)
    bad = 0
    checked = 0
    for p in packs:
        if not p["bundle_uid"] or not bundle_by[p["bundle_uid"]]["case_uid"]:
            continue
        b = bundle_by[p["bundle_uid"]]
        cs = case_by[b["case_uid"]]
        pal = pallet_by[cs["pallet_uid"]]
        t_com = t(p["commissioned_ts"])
        t_b, t_c = t(b["created_ts"]), t(cs["created_ts"])
        seq = [t_com, t_b, t_c]
        if pal["closed_ts"]:
            seq.append(t(pal["closed_ts"]))
        if pal["shipment_id"]:
            s = shipments[pal["shipment_id"]]
            if s["actual_departure"]:
                seq.append(t(s["actual_departure"]))
            if s["actual_arrival"]:
                seq.append(t(s["actual_arrival"]))
        checked += 1
        if any(a >= b2 for a, b2 in zip(seq, seq[1:])):
            bad += 1
    c.check("timestamps ordered: COMMISSION < AGGREGATE (bundle, case, pallet) < DISPATCH < ARRIVE",
            bad == 0, f"{checked} pack chains checked")
    c.check("no event after the snapshot time", all(t(e["ts"]) <= as_of for e in events))
    for s in shipments.values():
        if s["actual_departure"] and s["actual_arrival"] and t(s["actual_arrival"]) <= t(s["actual_departure"]):
            c.check("shipment arrival after departure", False, s["shipment_id"])
            break
    else:
        c.check("shipment arrival after departure", True)

    # KPI table agrees with unit-level rows in the detail window
    kpi_by_order = {k["order_id"]: k for k in kpi}
    pk_by_order = Counter(p["order_id"] for p in packs)
    detail_orders = set(pk_by_order)
    mism = [o for o in detail_orders if int(kpi_by_order[o]["packs_commissioned"]) != pk_by_order[o]]
    c.check("semantic-model packs_commissioned matches pack rows per order", not mism, f"{len(detail_orders)} orders")
    cs_by_order = Counter(x["order_id"] for x in cases)
    c.check("semantic-model cases_aggregated matches case rows", all(
        int(k["cases_aggregated"]) == cs_by_order[k["order_id"]] for k in kpi))

    # ---------------- S1 aggregation mismatch
    s1 = [x for x in cases if x["aggregation_status"] == "MISMATCH"]
    s1_lines = Counter((x["line_id"], x["created_ts"][:10]) for x in s1)
    c.check("S1: 120 cases with fewer bundles than expected on PL-02-L3 yesterday",
            s1_lines == Counter({("PL-02-L3", yday): 120}), str(dict(s1_lines)))
    c.check("S1: every mismatched case has bundle_count < expected",
            all(int(x["bundle_count"]) < int(x["expected_bundle_count"]) for x in s1))
    first = min(t(x["created_ts"]) for x in s1)
    fault = [m for m in mnt if m["line_id"] == "PL-02-L3" and m["maintenance_type"] == "SCANNER_FAULT"
             and m["ts"][:10] == yday]
    c.check("S1: scanner-fault maintenance entry 20 minutes before the mismatches start",
            len(fault) == 1 and timedelta(minutes=19) <= first - t(fault[0]["ts"]) <= timedelta(minutes=25),
            f"fault {fault[0]['ts'] if fault else '-'}, first mismatched case {first:%H:%M:%S}")
    deg = [r for r in tel if r["line_id"] == "PL-02-L3" and r["station"] == "CASE_AGGREGATION"
           and r["scanner_status"] == "DEGRADED"]
    c.check("S1: case-aggregation scanner telemetry degraded on PL-02-L3", len(deg) >= 100, f"{len(deg)} readings")
    other_long = 0
    run = defaultdict(int)
    for r in sorted(tel, key=lambda r: (r["line_id"], r["station"], r["ts"])):
        k = (r["line_id"], r["station"])
        run[k] = run[k] + 1 if r["read_rate_pct"] and float(r["read_rate_pct"]) < 98 else 0
        if run[k] > 3 and r["line_id"] != "PL-02-L3":
            other_long += 1
    c.check("S1: no other line has read rate < 98% for more than 15 minutes", other_long == 0)

    # ---------------- S2 delayed shipment to Market Beta
    delayed = [s for s in shipments.values() if s["status"] == "DELAYED"]
    s2 = delayed[0] if len(delayed) == 1 else None
    ok = bool(s2) and warehouse[s2["to_location"]]["market_id"] == "MKT-BETA" and \
        t(s2["actual_departure"]) - t(s2["planned_departure"]) == timedelta(hours=26)
    c.check("S2: exactly one DELAYED shipment, to Market Beta, departed 26 h late", ok,
            s2["shipment_id"] if s2 else str(len(delayed)))
    email_dir = os.path.join(args.data, "work-context", "emails")
    if s2 and os.path.isdir(email_dir):
        hit = any(s2["shipment_id"] in open(f, encoding="utf-8").read() for f in glob.glob(f"{email_dir}/*.eml"))
        c.check("S2: a partner email references the shipment_id", hit)

    # ---------------- S3 authority rejections
    rej = [s for s in subs if s["status"] == "REJECTED" and s["rejection_code"] == "MISSING_AGGREGATION_DATA"]
    linked = all(any(x["aggregation_status"] == "MISMATCH" for p in pallets if p["shipment_id"] == s["shipment_id"]
                     for x in cases if x["pallet_uid"] == p["pallet_uid"]) for s in rej)
    c.check("S3: 2 Market Gamma submissions REJECTED for missing aggregation data, linked to S1 cases",
            len(rej) == 2 and all(s["authority_id"] == "TA-GAMMA" for s in rej) and linked,
            ", ".join(s["submission_id"] for s in rej))
    open_rej = [s for s in subs if s["status"] == "REJECTED" and not any(
        r["resubmission_of"] == s["submission_id"] for r in subs)]
    c.check("S3: the only unresolved rejections are the two S3 submissions", {s["submission_id"] for s in open_rej} ==
            {s["submission_id"] for s in rej})

    # ---------------- S4 full trace
    readme = open(os.path.join(args.data, "README_data.md"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(args.data, "README_data.md")) else ""
    import re
    m = re.search(r"S4.*?(PK-[A-Z]{2}-\d{2}-[A-Z0-9]{8})", readme, re.S)
    if m:
        uid = m.group(1)
        p = next((x for x in packs if x["pack_uid"] == uid), None)
        ok = p is not None
        if ok:
            b = bundle_by[p["bundle_uid"]]
            cs = case_by[b["case_uid"]]
            pal = pallet_by[cs["pallet_uid"]]
            s = shipments[pal["shipment_id"]]
            wh = warehouse[s["to_location"]]
            subs_s = [x for x in subs if x["shipment_id"] == s["shipment_id"]]
            ok = (cs["aggregation_status"] == "COMPLETE" and s["status"] == "DELIVERED"
                  and wh["market_id"] == "MKT-BETA" and wh["warehouse_type"] == "DISTRIBUTOR"
                  and subs_s and all(x["status"] == "ACCEPTED" for x in subs_s))
            kinds = [e["event_type"] for uid2 in (uid, b["bundle_uid"], cs["case_uid"], pal["pallet_uid"])
                     for e in ev_by_obj[uid2]]
            ok = ok and kinds.count("DISPATCH") == 1 and kinds.count("ARRIVE") == 1
        c.check("S4: traced pack has a complete, clean chain to a Market Beta distributor", ok, uid)
    else:
        c.check("S4: pack UID listed in README_data.md", False)

    # ---------------- S5 supply risk
    latest = max(r["snapshot_date"] for r in inv)
    share = {w: float(r["demand_share_pct"]) / 100 for w, r in warehouse.items()}
    fwd = defaultdict(list)
    for r in fc:
        if r["forecast_date"] >= latest:
            fwd[(r["market_id"], r["sku"])].append((r["forecast_date"], int(r["forecast_qty"])))
    covers = {}
    for r in inv:
        if r["snapshot_date"] != latest:
            continue
        mk = warehouse[r["warehouse_id"]]["market_id"]
        nxt = sorted(fwd[(mk, r["sku"])])[:7]
        daily = sum(q for _, q in nxt) / len(nxt) * share[r["warehouse_id"]]
        covers[(r["warehouse_id"], r["sku"])] = int(r["qty_on_hand"]) / daily
    low = {k: v for k, v in covers.items() if v < 3}
    c.check("S5: only Beta North (WH-BET-D1) SKU-03 is below 3 days of cover",
            list(low) == [("WH-BET-D1", "SKU-03")], ", ".join(f"{k}={v:.1f}d" for k, v in low.items()))
    c.check("S5: Beta South (WH-BET-D2) holds surplus SKU-03 (> 7 days)", covers[("WH-BET-D2", "SKU-03")] > 7,
            f"{covers[('WH-BET-D2', 'SKU-03')]:.1f} days")

    # ---------------- S6 duplicate consumer scan
    dup = [s for s in scans if s["result"] == "DUPLICATE"]
    ok = len(dup) == 1
    if ok:
        prev = [s for s in scans if s["pack_uid"] == dup[0]["pack_uid"] and s["scan_id"] != dup[0]["scan_id"]]
        ok = len(prev) == 1 and prev[0]["country_code"] != dup[0]["country_code"] and \
            t(dup[0]["ts"]) - t(prev[0]["ts"]) < timedelta(hours=24)
    c.check("S6: one pack scanned in two distant countries within 24 h", ok)

    # ---------------- tutorial pages (rendered from generator/tutorial_templates)
    tdir = os.path.join(args.data, "tutorial")
    pages = sorted(f for f in os.listdir(tdir) if f.endswith(".md")) if os.path.isdir(tdir) else []
    text = "".join(open(os.path.join(tdir, f), encoding="utf-8").read() for f in pages)
    c.check("Tutorial: all pages rendered, no placeholders left", len(pages) == 11 and "{{" not in text,
            f"{len(pages)} pages")
    if m:
        c.check("Tutorial: S4 pack UID matches README_data.md", uid in text, uid)

    check_ontology(c, args.data, tdir)
    check_setup(c, args.data)

    print(f"\n{'All checks passed.' if c.failures == 0 else f'{c.failures} check(s) failed.'}")
    sys.exit(1 if c.failures else 0)


if __name__ == "__main__":
    main()
