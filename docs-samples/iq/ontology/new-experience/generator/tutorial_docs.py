"""Render the Track & Trace tutorial (tutorial/*.md) from the templates in tutorial_templates/.

Each template is Markdown with {{placeholders}}. The values come from the generated data (the
seeded scenarios S1-S6), so the IDs, times and numbers in the tutorial always match the CSV
files, also after regenerating with another --as-of. Edit the templates, not the output.
"""
from __future__ import annotations

import os
import re
import shutil
from collections import Counter
from datetime import timedelta

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tutorial_templates")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


def _day(d):
    """24 November 2026"""
    return f"{d.day} {d:%B %Y}"


def _day_short(d):
    """24 Nov"""
    return f"{d.day} {d:%b}"


def _ts(dt):
    """2026-11-24 06:42 UTC"""
    return f"{dt:%Y-%m-%d %H:%M} UTC"


def _when(dt):
    """24 Nov 06:42 UTC"""
    return f"{dt.day} {dt:%b %H:%M} UTC"


def _sent(v):
    """2026-11-24 06:47 from a datetime or an ISO-8601 string"""
    return f"{v:%Y-%m-%d %H:%M}" if hasattr(v, "strftime") else str(v)[:16].replace("T", " ")


def _n(x):
    return f"{x:,}"


def _pct(x):
    return f"{x:.1f}%".replace(".0%", "%")


def build_context(g, factories, partners):
    f = g.facts
    s1, s2, s3, s4, s5, s6 = f["s1"], f["s2"], f["s3"], f["s4"], f["s5"], f["s6"]
    yday, today = s1["day"], g.A
    partner_name = {p["partner_id"]: p["name"] for p in partners}
    factory_name = {x["factory_id"]: x["name"] for x in factories}
    ctx = {}

    # ---------------- general
    ctx.update(
        as_of=_ts(g.as_of),
        today=_day(today), today_long=f"{today:%A} {_day(today)}", today_iso=today.isoformat(),
        today_short=_day_short(today),
        yday=_day(yday), yday_long=f"{yday:%A} {_day(yday)}", yday_iso=yday.isoformat(),
        yday_short=_day_short(yday),
        period_start=_day(g.period_start), detail_start=_day(g.detail_start.date()),
        pack_parts=len(f.get("pack_parts", [])), seed=g.seed,
    )

    # ---------------- KPIs of "yesterday" per factory
    rows = [k for k in g.kpis if k["production_date"] == yday.isoformat()]
    lines = []
    tot = Counter()
    for fid in [x["factory_id"] for x in factories]:
        c = Counter()
        for k in rows:
            if k["factory_id"] == fid:
                for key in ("packs_commissioned", "planned_packs", "cases_aggregated", "cases_with_mismatch"):
                    c[key] += k[key]
        tot.update(c)
        rate = 100 * c["cases_with_mismatch"] / c["cases_aggregated"] if c["cases_aggregated"] else 0
        lines.append(f"| {fid} {factory_name[fid]} | {_n(c['packs_commissioned'])} | {_n(c['cases_aggregated'])} | "
                     f"{_n(c['cases_with_mismatch'])} | {_pct(rate)} |")
    rate = 100 * tot["cases_with_mismatch"] / tot["cases_aggregated"]
    lines.append(f"| **Total** | **{_n(tot['packs_commissioned'])}** | **{_n(tot['cases_aggregated'])}** | "
                 f"**{_n(tot['cases_with_mismatch'])}** | **{_pct(rate)}** |")
    ctx["kpi_table"] = "| Factory | Packs commissioned | Cases aggregated | Cases with mismatch | Aggregation error rate |\n" \
                       "|---|---:|---:|---:|---:|\n" + "\n".join(lines)
    ctx["packs_total"] = _n(tot["packs_commissioned"])
    line_kpi = next(k for k in rows if k["line_id"] == s1["line_id"])
    ctx["s1_line_cases"] = line_kpi["cases_aggregated"]
    ctx["s1_line_rate"] = _pct(100 * line_kpi["cases_with_mismatch"] / line_kpi["cases_aggregated"])

    # ---------------- S1 aggregation mismatch
    miss = Counter(c["expected_bundle_count"] - c["bundle_count"] for c in s1["cases"])
    sku1 = g.products[s1["sku"]]
    ctx.update(
        s1_line=s1["line_id"], s1_order=s1["order"]["order_id"], s1_sku=s1["sku"],
        s1_product=sku1["product_name"], s1_market=s1["order"]["target_market_id"],
        s1_cases=len(s1["cases"]), s1_miss1=miss.get(1, 0), s1_miss2=miss.get(2, 0),
        s1_bundles=s1["orphan_bundles"], s1_packs=_n(s1["orphan_packs"]),
        s1_first=f"{s1['first_case_ts']:%H:%M}", s1_last=f"{s1['last_case_ts']:%H:%M}",
        s1_fault=f"{s1['fault_ts']:%H:%M}", s1_bypass=f"{s1['bypass_ts']:%H:%M}",
        s1_repair=f"{s1['repair_ts']:%H:%M}",
        s1_fault_gap=int((s1["first_case_ts"] - s1["fault_ts"]).total_seconds() // 60),
    )
    ship_lines = []
    for i, sid in enumerate(s1["shipments"], start=1):
        sh = g.shipment_by_id[sid]
        n = sum(1 for p in sh["_pallets"] for c in p["_cases"] if c["aggregation_status"] == "MISMATCH")
        ctx[f"s1_ship{i}"] = sid
        ctx[f"s1_ship{i}_n"] = n
        ctx[f"s1_ship{i}_status"] = sh["status"]
        ctx[f"s1_ship{i}_cases"] = sh["case_count"]
        ctx[f"s1_ship{i}_dep"] = _when(sh["actual_departure"])
        ship_lines.append(f"`{sid}` ({sh['status']}, {n} of {sh['case_count']} cases affected)")
    ctx["s1_ships"] = " and ".join(ship_lines)
    ctx["s1_carrier"] = partner_name[g.shipment_by_id[s1["shipments"][0]]["partner_id"]]
    tel = [t for t in g.telemetry if t["line_id"] == s1["line_id"] and t["station"] == "CASE_AGGREGATION"
           and s1["bypass_ts"] <= t["ts"] < s1["repair_ts"] and t["read_rate_pct"] not in (None, "")]
    rates = [float(t["read_rate_pct"]) for t in tel]
    ctx["s1_read_min"] = f"{min(rates):.1f}%"
    ctx["s1_read_avg"] = f"{sum(rates) / len(rates):.1f}%"

    # ---------------- S3 authority rejections
    subs = s3["submissions"]
    ctx["s3_sub1"], ctx["s3_sub2"] = subs[0]["submission_id"], subs[1]["submission_id"]
    ctx["s3_subs"] = f"{subs[0]['submission_id']} and {subs[1]['submission_id']}"
    auth = subs[0]["authority_id"]
    ctx["s3_auth"] = auth
    ctx["s3_sla"] = next(int((s["sla_due_ts"] - s["event_ts"]).total_seconds() // 3600) for s in subs)

    # ---------------- S2 delayed shipment
    shp2 = s2["shipment"]
    wh2 = g.warehouses[shp2["to_location"]]
    ctx.update(
        s2_ship=shp2["shipment_id"], s2_carrier=partner_name[shp2["partner_id"]],
        s2_planned_dep=_when(shp2["planned_departure"]), s2_actual_dep=_when(shp2["actual_departure"]),
        s2_planned_arr=_when(shp2["planned_arrival"]), s2_eta=_when(shp2["estimated_arrival"]),
        s2_delay=f"{s2['delay_h']:.0f}", s2_pallets=shp2["pallet_count"], s2_cases=shp2["case_count"],
        s2_packs=_n(s2["packs"]), s2_wh=wh2["warehouse_id"], s2_wh_name=wh2["name"],
        s2_sku_split=", ".join(
            f"{sku} {g.products[sku]['brand_name']}: {v[0]} pallet{'s' if v[0] != 1 else ''} / {v[1]} cases"
            for sku, v in sorted(s2["by_sku"].items(), key=lambda kv: -kv[1][1])),
    )

    # ---------------- S4 full trace
    p4, sh4 = s4["pack"], s4["shipment"]
    subs4 = sorted((x for x in g.submissions if x["shipment_id"] == sh4["shipment_id"]),
                   key=lambda x: x["event_ts"])
    line4 = g.line_by_id[p4["line_id"]]
    ctx.update(
        s4_pack=p4["pack_uid"], s4_sku=p4["sku"], s4_product=g.products[p4["sku"]]["product_name"],
        s4_commissioned=_ts(p4["commissioned_ts"]), s4_line=p4["line_id"],
        s4_factory=f"{line4['factory_id']} {factory_name[line4['factory_id']]}", s4_order=p4["order_id"],
        s4_bundle=s4["bundle_uid"], s4_case=s4["case"]["case_uid"], s4_pallet=s4["pallet"]["pallet_uid"],
        s4_ship=sh4["shipment_id"], s4_carrier=partner_name[sh4["partner_id"]],
        s4_dispatched=_ts(sh4["actual_departure"]), s4_arrived=_ts(sh4["actual_arrival"]),
        s4_wh=s4["warehouse"]["warehouse_id"], s4_wh_name=s4["warehouse"]["name"],
        s4_subs=", ".join(f"{x['submission_id']} ({x['submission_type'].lower()}, {x['status']})" for x in subs4),
        s4_ref=f"BRS-TR-{g.A:%Y}-0417",
    )

    # ---------------- S5 supply risk
    d1, d2 = s5["d1_row"], s5["d2_row"]
    sku5 = g.products[d1["sku"]]
    cpp = sku5["cases_per_pallet"]
    release = max(0, d2["qty_on_hand"] - int(round(7 * s5["d2_daily"])))
    pallets = min(release // cpp, 6)
    move = pallets * cpp
    ctx.update(
        s5_sku=d1["sku"], s5_brand=sku5["brand_name"], s5_cpp=cpp,
        s5_d1=d1["warehouse_id"], s5_d1_name=g.warehouses[d1["warehouse_id"]]["name"],
        s5_d2=d2["warehouse_id"], s5_d2_name=g.warehouses[d2["warehouse_id"]]["name"],
        s5_d1_qty=d1["qty_on_hand"], s5_d1_transit=d1["qty_in_transit"], s5_d1_daily=f"{s5['d1_daily']:.0f}",
        s5_d1_cover=f"{s5['d1']:.1f}", s5_d2_qty=d2["qty_on_hand"], s5_d2_daily=f"{s5['d2_daily']:.0f}",
        s5_d2_cover=f"{s5['d2']:.1f}", s5_release=release, s5_pallets=pallets, s5_move=move,
        s5_d1_after=f"{(d1['qty_on_hand'] + move) / s5['d1_daily']:.1f}",
        s5_d2_after=f"{(d2['qty_on_hand'] - move) / s5['d2_daily']:.1f}",
        s5_runout=_day(today + timedelta(days=int(s5["d1"]))),
    )

    # ---------------- S6 consumer scans
    scans = sorted((s for s in g.scans if s["pack_uid"] == s6["pack_uid"]), key=lambda s: s["ts"])
    ctx.update(
        s6_pack=s6["pack_uid"], s6_t1=_when(s6["t1"]), s6_t2=_when(s6["t2"]),
        s6_hours=f"{(s6['t2'] - s6['t1']).total_seconds() / 3600:.1f}",
        s6_where1=f"{scans[0]['country_code']} ({scans[0]['city']})",
        s6_where2=f"{scans[-1]['country_code']} ({scans[-1]['city']})",
        s6_km=_n(int(float(scans[-1]["distance_from_previous_scan_km"]))),
        s6_unknown=sum(1 for s in g.scans if s["result"] == "UNKNOWN"),
    )

    # ---------------- work context
    mails = f.get("emails", [])
    teams = f.get("teams", [])
    rel = [m for m in mails if m["relevant"]]
    ctx["email_count"] = len(mails)
    ctx["email_relevant"] = len(rel)
    ctx["email_noise"] = len(mails) - len(rel)
    ctx["email_table"] = "| Email | Sent (UTC) | From | Subject | Scenario |\n|---|---|---|---|---|\n" + "\n".join(
        f"| {m['email_id']} | {_sent(m['sent'])} | {m['from_name']} | {m['subject']} | {m['scenario']} |"
        for m in rel)
    trel = [m for m in teams if m["relevant"]]
    ctx["teams_count"] = len(teams)
    ctx["teams_relevant"] = ", ".join(m["message_id"] for m in trel)
    ctx["teams_table"] = "| Message | Sent (UTC) | From | Text |\n|---|---|---|---|\n" + "\n".join(
        f"| {m['message_id']} | {_sent(m['sent'])} | {m['from']} | {m['text']} |" for m in trel)
    return ctx


def render(text, ctx, name):
    missing = sorted({k for k in PLACEHOLDER.findall(text) if k not in ctx})
    if missing:
        raise KeyError(f"{name}: unknown placeholder(s) {', '.join(missing)}")

    def sub(m):
        value = str(ctx[m.group(1)])
        # A multi-line value (a table) placed on an indented line keeps that indentation on every line,
        # so it stays inside the surrounding list item.
        line_start = text.rfind("\n", 0, m.start()) + 1
        indent = text[line_start:m.start()]
        if indent and not indent.strip():
            value = value.replace("\n", "\n" + indent)
        return value

    return PLACEHOLDER.sub(sub, text)


def write_tutorial(g, out, factories, partners):
    """Render every template into <out>/tutorial/ and return the written file names."""
    ctx = build_context(g, factories, partners)
    target = os.path.join(out, "tutorial")
    shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target)
    written = []
    for name in sorted(os.listdir(TEMPLATE_DIR)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as fh:
            text = render(fh.read(), ctx, name)
        header = (f"<!-- Generated by generator/generate_data.py from generator/tutorial_templates/{name}. "
                  f"Edit the template, then run the generator again. -->\n")
        with open(os.path.join(target, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(header + text)
        written.append(name)
    return written
