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
import os
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

    print(f"\n{'All checks passed.' if c.failures == 0 else f'{c.failures} check(s) failed.'}")
    sys.exit(1 if c.failures else 0)


if __name__ == "__main__":
    main()
