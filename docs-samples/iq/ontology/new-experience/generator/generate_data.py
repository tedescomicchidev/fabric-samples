#!/usr/bin/env python3
"""Synthetic data generator for the Track & Trace edition of the Fabric IQ ontology tutorial.

Everything this script writes is synthetic. Factories, brands, markets, tax authorities,
partners, people and identifiers are fictional. No real company, vendor, factory, market,
customer or tax-authority data is used.

What it produces (relative to --out, default: the parent folder of this script):

    lakehouse/                 CSV files to upload to the lakehouse (one table per file or folder)
    lakehouse/pack/            the pack table, split into parts (load the folder as one table)
    eventhouse/                CSV files for the KQL database (TraceEvent, LineScannerTelemetry)
    semantic-model/            source data of the KPI semantic model (reference only)
    notebooks/                 notebook that creates the KPI semantic model in your workspace
    work-context/              emails, Teams messages and SOPs for the Work IQ side of the demo
    README_data.md             row counts and where each seeded scenario lives
    TUTORIAL_GUIDE.md          how to run the Fabric IQ ontology tutorial with this data

Usage:
    python generate_data.py
    python generate_data.py --out /tmp/tt-demo --as-of 2026-11-25T07:00:00Z --seed 20261125

Only the Python standard library is used, and every random draw comes from
random.Random.random(), whose sequence Python guarantees across versions. The same --seed
and --as-of therefore always produce identical files.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docs_templates  # noqa: E402
import work_context  # noqa: E402

UTC = timezone.utc
DEFAULT_AS_OF = "2026-11-25T07:00:00Z"
DEFAULT_SEED = 20261125
PART_MAX_BYTES = 3_900_000  # keeps every file small enough for browser uploads and Git hosting
PERIOD_DAYS = 30
FORECAST_DAYS_AHEAD = 14
TELEMETRY_HOURS = 72
MAX_PALLETS_PER_SHIPMENT = 26
PALLET_CUTOFF_MINUTES = 60  # a pallet must be closed this long before departure to make the truck


# --------------------------------------------------------------------------------------
# Deterministic random helpers (only random.Random.random() is used)
# --------------------------------------------------------------------------------------
class Rng:
    UID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self, seed: int):
        self._r = random.Random(seed)

    def random(self) -> float:
        return self._r.random()

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._r.random()

    def randint(self, a: int, b: int) -> int:
        return a + int(self._r.random() * (b - a + 1))

    def chance(self, p: float) -> bool:
        return self._r.random() < p

    def choice(self, seq):
        return seq[int(self._r.random() * len(seq))]

    def gauss(self, mu: float, sigma: float) -> float:
        u1 = max(self._r.random(), 1e-12)
        u2 = self._r.random()
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)

    def shuffle(self, items: list) -> None:
        for i in range(len(items) - 1, 0, -1):
            j = int(self._r.random() * (i + 1))
            items[i], items[j] = items[j], items[i]

    def sample(self, seq, k: int) -> list:
        pool = list(seq)
        self.shuffle(pool)
        return pool[:k]

    def code(self, n: int = 8) -> str:
        a = self.UID_ALPHABET
        return "".join(a[int(self._r.random() * len(a))] for _ in range(n))


def ts(dt: datetime | None) -> str:
    return "" if dt is None else dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def dstr(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=UTC)


# --------------------------------------------------------------------------------------
# Master data (all fictional)
# --------------------------------------------------------------------------------------
FACTORIES = [
    {"factory_id": "PL-01", "name": "Oakridge Plant", "country_code": "PL", "timezone": "Europe/Warsaw"},
    {"factory_id": "PL-02", "name": "Riverbend Plant", "country_code": "PL", "timezone": "Europe/Warsaw"},
    {"factory_id": "CZ-01", "name": "Silverbrook Plant", "country_code": "CZ", "timezone": "Europe/Prague"},
]

LINE_TYPES = {
    # rated output in shipping cases per hour (round demo numbers, not real line speeds)
    "CIG_HIGH_SPEED": {"rate": 10, "category": "Cigarettes"},
    "CIG_STANDARD": {"rate": 3, "category": "Cigarettes"},
    "HTS": {"rate": 5, "category": "Heated tobacco sticks"},
}

LINE_LAYOUT = {
    "PL-01": ["CIG_HIGH_SPEED", "CIG_STANDARD", "CIG_STANDARD", "HTS"],
    "PL-02": ["CIG_STANDARD", "CIG_STANDARD", "CIG_HIGH_SPEED", "HTS"],
    "CZ-01": ["CIG_STANDARD", "CIG_HIGH_SPEED", "CIG_STANDARD", "HTS"],
}

SCANNER_MODELS = {"CIG_HIGH_SPEED": "VisionAgg 4000", "CIG_STANDARD": "VisionAgg 2500", "HTS": "VisionAgg 3000"}

PRODUCTS = [
    # sku, brand, product name, category, packs/bundle, bundles/case, cases/pallet
    ("SKU-01", "Horizon Blue", "Horizon Blue KS 20", "Cigarettes", 10, 5, 20),
    ("SKU-02", "Nova Gold", "Nova Gold KS 20", "Cigarettes", 10, 5, 20),
    ("SKU-03", "Orion Red", "Orion Red KS 20", "Cigarettes", 10, 5, 20),
    ("SKU-04", "Glacier Silver", "Glacier Silver Super Slims 20", "Cigarettes", 10, 4, 25),
    ("SKU-05", "Meridian White", "Meridian White KS 20", "Cigarettes", 10, 5, 20),
    ("SKU-06", "Vega Black", "Vega Black KS 20", "Cigarettes", 10, 5, 20),
    ("SKU-07", "Aurora Green", "Aurora Green Heated Sticks 20", "Heated tobacco sticks", 10, 5, 24),
    ("SKU-08", "Solstice Amber", "Solstice Amber Heated Sticks 20", "Heated tobacco sticks", 10, 5, 24),
]

MARKETS = [
    {"market_id": "MKT-ALPHA", "name": "Market Alpha", "country_code": "XA",
     "regulation_profile": "DISPATCH_AND_ARRIVAL", "requires_stamp": False},
    {"market_id": "MKT-BETA", "name": "Market Beta", "country_code": "XB",
     "regulation_profile": "TAX_STAMP_RECONCILIATION", "requires_stamp": True},
    {"market_id": "MKT-GAMMA", "name": "Market Gamma", "country_code": "XC",
     "regulation_profile": "FULL_HIERARCHY_AT_DISPATCH", "requires_stamp": True},
    {"market_id": "MKT-DELTA", "name": "Market Delta", "country_code": "XD",
     "regulation_profile": "ARRIVAL_ONLY", "requires_stamp": False},
]

REQUIRED_SUBMISSIONS = {
    "DISPATCH_AND_ARRIVAL": ["DISPATCH", "ARRIVAL"],
    "TAX_STAMP_RECONCILIATION": ["DISPATCH", "ARRIVAL"],
    "FULL_HIERARCHY_AT_DISPATCH": ["DISPATCH"],
    "ARRIVAL_ONLY": ["ARRIVAL"],
}

TAX_AUTHORITIES = [
    {"authority_id": "TA-ALPHA", "market_id": "MKT-ALPHA", "name": "Alpha Excise Authority",
     "submission_sla_hours": 24, "contact_email": "tt-desk@excise-alpha.example.test"},
    {"authority_id": "TA-BETA", "market_id": "MKT-BETA", "name": "Beta Revenue and Stamp Office",
     "submission_sla_hours": 12, "contact_email": "trace-requests@revenue-beta.example.test"},
    {"authority_id": "TA-GAMMA", "market_id": "MKT-GAMMA", "name": "Gamma Customs and Excise Agency",
     "submission_sla_hours": 4, "contact_email": "no-reply@excise-gamma.example.test"},
    {"authority_id": "TA-DELTA", "market_id": "MKT-DELTA", "name": "Delta Tax Administration",
     "submission_sla_hours": 48, "contact_email": "tracking@tax-delta.example.test"},
]

PARTNERS = [
    {"partner_id": "PRT-01", "name": "Vistaline Freight", "partner_type": "CARRIER",
     "contact_email": "ops.vistaline@example-logistics.test"},
    {"partner_id": "PRT-02", "name": "Northgate Haulage", "partner_type": "CARRIER",
     "contact_email": "ops.northgate@example-logistics.test"},
    {"partner_id": "PRT-03", "name": "Blueway Transport", "partner_type": "CARRIER",
     "contact_email": "dispatch.blueway@example-logistics.test"},
    {"partner_id": "PRT-04", "name": "Meridian 3PL Services", "partner_type": "THIRD_PARTY_LOGISTICS",
     "contact_email": "beta.ops.meridian@example-logistics.test"},
    {"partner_id": "PRT-05", "name": "Clearpath Customs Brokers", "partner_type": "CUSTOMS_BROKER",
     "contact_email": "desk.clearpath@example-logistics.test"},
]

WAREHOUSES = [
    {"warehouse_id": "WH-ALP-H1", "name": "Alpha Central Hub", "market_id": "MKT-ALPHA",
     "warehouse_type": "HUB", "demand_share_pct": 65, "operator_partner_id": ""},
    {"warehouse_id": "WH-ALP-D1", "name": "Alpha East Distributor", "market_id": "MKT-ALPHA",
     "warehouse_type": "DISTRIBUTOR", "demand_share_pct": 35, "operator_partner_id": ""},
    {"warehouse_id": "WH-BET-D1", "name": "Beta North Distributor", "market_id": "MKT-BETA",
     "warehouse_type": "DISTRIBUTOR", "demand_share_pct": 60, "operator_partner_id": "PRT-04"},
    {"warehouse_id": "WH-BET-D2", "name": "Beta South Distributor", "market_id": "MKT-BETA",
     "warehouse_type": "DISTRIBUTOR", "demand_share_pct": 40, "operator_partner_id": "PRT-04"},
    {"warehouse_id": "WH-GAM-H1", "name": "Gamma National Hub", "market_id": "MKT-GAMMA",
     "warehouse_type": "HUB", "demand_share_pct": 100, "operator_partner_id": ""},
    {"warehouse_id": "WH-DEL-H1", "name": "Delta Import Hub", "market_id": "MKT-DELTA",
     "warehouse_type": "HUB", "demand_share_pct": 100, "operator_partner_id": ""},
]

# Market sell-out demand in shipping cases per day (base, before weekday profile)
MARKET_DEMAND = {
    "MKT-ALPHA": {"SKU-01": 50, "SKU-02": 40, "SKU-04": 30, "SKU-05": 35, "SKU-07": 35, "SKU-08": 30},
    "MKT-BETA": {"SKU-01": 45, "SKU-03": 60, "SKU-05": 30, "SKU-06": 35, "SKU-07": 30},
    "MKT-GAMMA": {"SKU-02": 55, "SKU-03": 35, "SKU-06": 40, "SKU-08": 30},
    "MKT-DELTA": {"SKU-01": 30, "SKU-04": 25, "SKU-05": 30, "SKU-07": 25},
}
WEEKDAY_PROFILE = [0.92, 0.95, 1.0, 1.05, 1.2, 1.15, 0.73]  # Mon..Sun

# Scheduled line-haul lanes: factory -> warehouse, carrier, transit hours, departures (weekday, hh, mm)
LANES = [
    ("PL-01", "WH-ALP-H1", "PRT-01", 14, [(0, 13, 30), (2, 13, 30), (4, 13, 30)]),
    ("PL-01", "WH-BET-D1", "PRT-02", 18, [(0, 14, 0), (3, 14, 0)]),
    ("PL-01", "WH-BET-D2", "PRT-02", 18, [(1, 21, 30), (4, 21, 30)]),
    ("PL-02", "WH-GAM-H1", "PRT-01", 10, [(w, 13, 30) for w in range(6)] + [(w, 21, 30) for w in range(5)]),
    ("PL-02", "WH-ALP-D1", "PRT-01", 14, [(1, 13, 30), (4, 13, 30)]),
    ("PL-02", "WH-DEL-H1", "PRT-03", 30, [(2, 13, 30), (5, 13, 30)]),
    ("CZ-01", "WH-ALP-H1", "PRT-03", 12, [(1, 13, 30), (3, 13, 30)]),
    ("CZ-01", "WH-DEL-H1", "PRT-03", 26, [(0, 21, 30), (3, 21, 30)]),
    ("CZ-01", "WH-BET-D2", "PRT-02", 20, [(2, 13, 30), (5, 13, 30)]),
    ("CZ-01", "WH-GAM-H1", "PRT-03", 16, [(4, 13, 30)]),
]

CONSUMER_CITIES = {
    "XA": ["Alpha City", "Northport", "Eastvale"],
    "XB": ["Beta City", "Lakeview", "Southmere"],
    "XC": ["Gamma City", "Westford"],
    "XD": ["Delta City", "Harbourton"],
}


# --------------------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------------------
class Generator:
    def __init__(self, as_of: datetime, seed: int):
        if as_of.weekday() != 2:
            raise SystemExit("--as-of must be a Wednesday so the seeded storyline lines up "
                             "(the default is Wednesday 2026-11-25 07:00 UTC).")
        self.as_of = as_of
        self.seed = seed
        self.A = as_of.date()  # demo day (Wednesday)
        self.period_start = self.A - timedelta(days=PERIOD_DAYS - 1)
        self.detail_start = at(self.A - timedelta(days=5), 0)  # Friday 00:00 UTC
        self.telemetry_start = as_of - timedelta(hours=TELEMETRY_HOURS)
        self.s1_day = self.A - timedelta(days=1)  # Tuesday = "yesterday"

        self.r_plan = Rng(seed * 10 + 1)
        self.r_units = Rng(seed * 10 + 2)
        self.r_ship = Rng(seed * 10 + 3)
        self.r_inv = Rng(seed * 10 + 4)
        self.r_misc = Rng(seed * 10 + 5)
        self.r_tel = Rng(seed * 10 + 6)
        self.r_scan = Rng(seed * 10 + 7)

        self.products = {p[0]: {
            "sku": p[0], "brand_name": p[1], "product_name": p[2], "category": p[3],
            "packs_per_bundle": p[4], "bundles_per_case": p[5], "cases_per_pallet": p[6],
            "packs_per_case": p[4] * p[5], "packs_per_pallet": p[4] * p[5] * p[6], "sticks_per_pack": 20,
        } for p in PRODUCTS}
        self.markets = {m["market_id"]: m for m in MARKETS}
        self.warehouses = {w["warehouse_id"]: w for w in WAREHOUSES}
        self.authority_by_market = {a["market_id"]: a for a in TAX_AUTHORITIES}
        self.lines = []
        for f in FACTORIES:
            for i, lt in enumerate(LINE_LAYOUT[f["factory_id"]], start=1):
                self.lines.append({
                    "line_id": f"{f['factory_id']}-L{i}", "factory_id": f["factory_id"],
                    "line_name": f"Line {i}", "line_type": lt, "status": "ACTIVE",
                    "rated_cases_per_hour": LINE_TYPES[lt]["rate"],
                    "aggregation_scanner_model": SCANNER_MODELS[lt],
                    "commissioned_date": "",
                })
        for ln in self.lines:
            ln["commissioned_date"] = dstr(date(2019 + self.r_misc.randint(0, 5), self.r_misc.randint(1, 12), 1))
        self.maint_line = "CZ-01-L4"
        self.maint_from = self.A - timedelta(days=6)  # Thursday before the demo
        self.maint_to = self.A + timedelta(days=3)
        for ln in self.lines:
            if ln["line_id"] == self.maint_line:
                ln["status"] = "PLANNED_MAINTENANCE"
        self.line_by_id = {ln["line_id"]: ln for ln in self.lines}
        self.lanes = [{"factory_id": l[0], "warehouse_id": l[1], "partner_id": l[2],
                       "transit_hours": l[3], "departures": l[4]} for l in LANES]

        # Scenario anchors
        self.overrides = {
            ("PL-01-L1", self.A - timedelta(days=5)): ("SKU-01", "WH-BET-D2"),  # S4 source order
            ("PL-01-L1", self.A - timedelta(days=4)): ("SKU-03", "WH-BET-D1"),  # S2 cargo
            ("PL-01-L1", self.A - timedelta(days=2)): ("SKU-03", "WH-BET-D1"),  # S2 cargo
            ("PL-02-L3", self.s1_day): ("SKU-02", "WH-GAM-H1"),                 # S1 order
        }
        self.s1_line = "PL-02-L3"
        self.s1_fault_ts = at(self.s1_day, 6, 20)
        self.s1_bypass_ts = at(self.s1_day, 6, 38)
        self.s1_first_mismatch = at(self.s1_day, 6, 40)
        self.s1_repair_ts = at(self.s1_day, 18, 40)
        self.s2_lane = ("PL-01", "WH-BET-D1")
        self.s2_planned_departure = at(self.A - timedelta(days=2), 14, 0)
        self.s2_departure_delay = timedelta(hours=26)

        self.used_uids: set[str] = set()
        self.tables: dict[str, list[dict]] = {}
        self.facts: dict = {}

    # ---------------------------------------------------------------- helpers
    def uid(self, prefix: str, factory_id: str) -> str:
        while True:
            u = f"{prefix}-{factory_id}-{self.r_units.code(8)}"
            if u not in self.used_uids:
                self.used_uids.add(u)
                return u

    def days(self):
        d = self.period_start
        while d <= self.A:
            yield d
            d += timedelta(days=1)

    def market_daily(self, market_id: str, sku: str, d: date) -> float:
        return MARKET_DEMAND[market_id][sku] * WEEKDAY_PROFILE[d.weekday()]

    def wh_daily(self, wh_id: str, sku: str, d: date) -> float:
        w = self.warehouses[wh_id]
        return self.market_daily(w["market_id"], sku, d) * w["demand_share_pct"] / 100.0

    def shift_window(self, d: date):
        wd = d.weekday()
        if wd <= 4:
            return at(d, 5), at(d, 21)
        if wd == 5:
            return at(d, 5), at(d, 13)
        return None

    # ---------------------------------------------------------------- planning
    def plan_production(self):
        combos = []
        lanes_by_factory = defaultdict(set)
        for ln in self.lanes:
            lanes_by_factory[ln["factory_id"]].add(ln["warehouse_id"])
        for w in WAREHOUSES:
            for sku in MARKET_DEMAND[w["market_id"]]:
                combos.append((w["warehouse_id"], sku))
        init_days = 7.0
        planned = defaultdict(float)
        lead = 3
        orders = []
        for d in self.days():
            window = self.shift_window(d)
            if window is None:
                continue
            for ln in self.lines:
                lid = ln["line_id"]
                if lid == self.maint_line and self.maint_from <= d <= self.maint_to:
                    continue
                key = (lid, d)
                if key in self.overrides:
                    sku, wh = self.overrides[key]
                else:
                    if self.r_plan.chance(0.05):
                        continue  # changeover / no material
                    cat = LINE_TYPES[ln["line_type"]]["category"]
                    best, best_cover = None, None
                    for wh_id, sku in combos:
                        if wh_id not in lanes_by_factory[ln["factory_id"]]:
                            continue
                        if self.products[sku]["category"] != cat:
                            continue
                        if (wh_id, sku) == ("WH-BET-D1", "SKU-03") and d >= self.A - timedelta(days=9):
                            continue  # supplied only by the scenario orders near the demo date
                        daily = self.wh_daily(wh_id, sku, d)
                        demand_to_date = sum(self.wh_daily(wh_id, sku, self.period_start + timedelta(days=k))
                                             for k in range((d - self.period_start).days + lead + 1))
                        stock_proj = init_days * daily + planned[(wh_id, sku)] - demand_to_date
                        cover = stock_proj / daily
                        if best_cover is None or cover < best_cover:
                            best, best_cover = (wh_id, sku), cover
                    if best is None or best_cover > 10:
                        continue
                    wh, sku = best
                rate = ln["rated_cases_per_hour"]
                start, end = window
                hours = (end - start).total_seconds() / 3600
                eff = 1.0 if key == (self.s1_line, self.s1_day) else round(self.r_plan.uniform(0.88, 0.98), 3)
                cases_full = int(round(rate * hours * eff))
                planned[(wh, sku)] += cases_full
                orders.append({"line": ln, "date": d, "sku": sku, "warehouse_id": wh,
                               "start": start, "end": end, "eff": eff, "cases_full": cases_full,
                               "rate": rate})
        self.plan = orders

    # ---------------------------------------------------------------- units
    def build_units(self):
        packs, bundles, cases, pallets, orders, events = [], [], [], [], [], []
        kpis = []
        decom_rng = self.r_units
        s1_cases = []
        for o in self.plan:
            ln, d, sku = o["line"], o["date"], o["sku"]
            p = self.products[sku]
            fid = ln["factory_id"]
            wh = self.warehouses[o["warehouse_id"]]
            order_id = f"PO-{d:%Y%m%d}-{ln['line_id'].replace('-', '')}"
            interval = (o["end"] - o["start"]) / o["cases_full"]
            n_cases = o["cases_full"]
            in_progress = o["end"] > self.as_of
            if in_progress:
                n_cases = int((self.as_of - o["start"]) / interval)
            case_times = [o["start"] + interval * (k + 1) for k in range(n_cases)]
            detail = o["start"] >= self.detail_start
            is_s1 = (ln["line_id"], d) == (self.s1_line, self.s1_day)
            ppb, bpc, cpp = p["packs_per_bundle"], p["bundles_per_case"], p["cases_per_pallet"]
            order_cases, order_bundles_agg, order_decom, order_packs = [], 0, 0, 0
            for k, cts in enumerate(case_times):
                case_uid = self.uid("CS", fid)
                missing = 0
                agg_status = "COMPLETE"
                if is_s1 and self.s1_first_mismatch <= cts < self.s1_repair_ts:
                    missing = 1 if self.r_units.chance(0.7) else 2
                    agg_status = "MISMATCH"
                elif self.r_units.chance(0.0012) and cts + timedelta(minutes=100) < self.as_of:
                    agg_status = "REWORKED"
                bundle_count = bpc - missing
                case = {"case_uid": case_uid, "pallet_uid": "", "line_id": ln["line_id"], "order_id": order_id,
                        "sku": sku, "created_ts": cts, "expected_bundle_count": bpc,
                        "bundle_count": bundle_count, "aggregation_status": agg_status}
                cases.append(case)
                order_cases.append(case)
                order_bundles_agg += bundle_count
                if agg_status == "MISMATCH":
                    s1_cases.append(case)
                events.append(dict(object_uid=case_uid, object_level="CASE", event_type="AGGREGATE", ts=cts,
                                   location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                   child_count=bundle_count, shipment_id=""))
                if agg_status == "REWORKED":
                    t1 = cts + timedelta(minutes=self.r_units.randint(15, 90))
                    events.append(dict(object_uid=case_uid, object_level="CASE", event_type="DISAGGREGATE", ts=t1,
                                       location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                       child_count=bpc - 1, shipment_id=""))
                    events.append(dict(object_uid=case_uid, object_level="CASE", event_type="AGGREGATE",
                                       ts=t1 + timedelta(minutes=4), location_id=ln["line_id"],
                                       source_system="LINE_SERIALIZATION", child_count=bpc, shipment_id=""))
                order_packs += bpc * ppb
                if not detail:
                    continue
                # unit-level detail (bundles and packs) for production inside the detail window
                missing_idx = set(self.r_units.sample(range(bpc), missing)) if missing else set()
                bundle_span = interval / bpc
                for j in range(bpc):
                    bts = cts - interval + bundle_span * (j + 1) - timedelta(seconds=20)
                    bundle_uid = self.uid("BU", fid)
                    orphan = j in missing_idx
                    bundles.append({"bundle_uid": bundle_uid, "case_uid": "" if orphan else case_uid,
                                    "line_id": ln["line_id"], "order_id": order_id, "sku": sku,
                                    "created_ts": bts, "pack_count": ppb,
                                    "status": "NOT_AGGREGATED" if orphan else "AGGREGATED"})
                    events.append(dict(object_uid=bundle_uid, object_level="BUNDLE", event_type="AGGREGATE",
                                       ts=bts, location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                       child_count=ppb, shipment_id=""))
                    pack_span = bundle_span / (ppb + 1)
                    for i in range(ppb):
                        pts = bts - bundle_span + pack_span * (i + 1)
                        pack_uid = self.uid("PK", fid)
                        packs.append({"pack_uid": pack_uid, "sku": sku, "order_id": order_id,
                                      "line_id": ln["line_id"], "bundle_uid": bundle_uid,
                                      "commissioned_ts": pts, "_case": None if orphan else case,
                                      "status": "AGGREGATION_INCOMPLETE" if orphan else "AGGREGATED"})
                        events.append(dict(object_uid=pack_uid, object_level="PACK", event_type="COMMISSION",
                                           ts=pts, location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                           child_count="", shipment_id=""))
            # decommissioned packs (QA rejects removed before bundling; they never get a bundle)
            n_decom = int(round(len(order_cases) * bpc * ppb * self.r_units.uniform(0.001, 0.004)))
            order_decom = n_decom
            if detail and order_cases:
                last_ok = min(case_times[-1], self.as_of - timedelta(minutes=5))
                for _ in range(n_decom):
                    pts = o["start"] + (last_ok - o["start"]) * self.r_units.random()
                    pack_uid = self.uid("PK", fid)
                    packs.append({"pack_uid": pack_uid, "sku": sku, "order_id": order_id, "line_id": ln["line_id"],
                                  "bundle_uid": "", "commissioned_ts": pts, "_case": None,
                                  "status": "DECOMMISSIONED"})
                    events.append(dict(object_uid=pack_uid, object_level="PACK", event_type="COMMISSION", ts=pts,
                                       location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                       child_count="", shipment_id=""))
                    events.append(dict(object_uid=pack_uid, object_level="PACK", event_type="DECOMMISSION",
                                       ts=pts + timedelta(seconds=self.r_units.randint(40, 240)),
                                       location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                       child_count="", shipment_id=""))
            # pallets
            order_pallets = []
            for g in range(0, len(order_cases), cpp):
                group = order_cases[g:g + cpp]
                full = len(group) == cpp
                last_of_order = g + cpp >= len(order_cases)
                pallet_uid = self.uid("PAL", fid)
                if in_progress and last_of_order and (
                        not full or group[-1]["created_ts"] + timedelta(minutes=3) > self.as_of):
                    status, closed = "OPEN", None
                else:
                    status, closed = "READY", group[-1]["created_ts"] + timedelta(minutes=3)
                pal = {"pallet_uid": pallet_uid, "shipment_id": "", "line_id": ln["line_id"],
                       "order_id": order_id, "sku": sku, "destination_warehouse_id": wh["warehouse_id"],
                       "factory_id": fid, "created_ts": group[0]["created_ts"], "closed_ts": closed,
                       "case_count": len(group), "status": status, "_cases": group}
                for c in group:
                    c["pallet_uid"] = pallet_uid
                    c["_pallet"] = pal
                pallets.append(pal)
                order_pallets.append(pal)
                if closed is not None:
                    events.append(dict(object_uid=pallet_uid, object_level="PALLET", event_type="AGGREGATE",
                                       ts=closed, location_id=ln["line_id"], source_system="LINE_SERIALIZATION",
                                       child_count=len(group), shipment_id=""))
            planned_qty = int(round(o["rate"] * (o["end"] - o["start"]).total_seconds() / 3600)) * bpc * ppb
            produced_cases = len(order_cases)
            end_actual = case_times[-1] if case_times else o["start"]
            orders.append({
                "order_id": order_id, "line_id": ln["line_id"], "sku": sku,
                "target_market_id": wh["market_id"], "destination_warehouse_id": wh["warehouse_id"],
                "planned_qty": planned_qty, "produced_qty": produced_cases * bpc * ppb, "uom": "PACK",
                "start_ts": o["start"], "end_ts": o["end"] if in_progress else end_actual,
                "status": "IN_PROGRESS" if in_progress else "COMPLETED",
                "_actual_end": end_actual,
            })
            kpis.append({
                "production_date": dstr(d), "factory_id": fid, "line_id": ln["line_id"], "order_id": order_id,
                "sku": sku, "target_market_id": wh["market_id"], "planned_packs": planned_qty,
                "packs_commissioned": order_packs + order_decom, "packs_decommissioned": order_decom,
                "bundles_aggregated": order_bundles_agg, "cases_aggregated": produced_cases,
                "cases_with_mismatch": sum(1 for c in order_cases if c["aggregation_status"] != "COMPLETE"),
                "pallets_built": len(order_pallets),
            })
        self.packs, self.bundles, self.cases, self.pallets = packs, bundles, cases, pallets
        self.orders, self.events, self.kpis = orders, events, kpis
        self.s1_cases = s1_cases

    # ---------------------------------------------------------------- shipments
    def build_shipments(self):
        shipments = []
        horizon = self.as_of + timedelta(days=3)
        by_lane = defaultdict(list)
        for p in self.pallets:
            if p["status"] == "READY":
                by_lane[(p["factory_id"], p["destination_warehouse_id"])].append(p)
        for lst in by_lane.values():
            lst.sort(key=lambda x: x["closed_ts"])
        for lane in self.lanes:
            key = (lane["factory_id"], lane["warehouse_id"])
            queue = by_lane.get(key, [])
            deps = []
            d = self.period_start
            while d <= horizon.date():
                for wd, hh, mm in lane["departures"]:
                    if d.weekday() == wd:
                        deps.append(at(d, hh, mm))
                d += timedelta(days=1)
            deps.sort()
            future_used = False
            for dep in deps:
                if dep > horizon:
                    break
                if dep > self.as_of and future_used:
                    break
                cutoff = dep - timedelta(minutes=PALLET_CUTOFF_MINUTES)
                if dep > self.as_of:
                    cutoff = min(cutoff, self.as_of)
                load = [p for p in queue if p["shipment_id"] == "" and p["closed_ts"] <= cutoff]
                if not load:
                    continue
                load = load[:MAX_PALLETS_PER_SHIPMENT]
                if dep > self.as_of:
                    future_used = True
                sid = f"SHP-{dep:%Y%m%d}-{lane['factory_id'].replace('-', '')}-{lane['warehouse_id'][3:].replace('-', '')}"
                if dep.hour >= 18:
                    sid += "-E"
                transit = timedelta(hours=lane["transit_hours"])
                planned_arr = dep + transit
                is_s2 = key == self.s2_lane and dep == self.s2_planned_departure
                if is_s2:
                    act_dep = dep + self.s2_departure_delay
                    est_arr = planned_arr + self.s2_departure_delay + timedelta(hours=4)
                    act_arr = None
                else:
                    delay = timedelta(minutes=self.r_ship.randint(0, 40))
                    if dep < self.as_of - timedelta(days=4) and self.r_ship.chance(0.04):
                        delay = timedelta(minutes=self.r_ship.randint(180, 540))
                    act_dep = dep + delay
                    act_arr = act_dep + transit + timedelta(minutes=self.r_ship.randint(-45, 90))
                    est_arr = planned_arr + delay
                if act_dep > self.as_of:
                    status, act_dep_v, act_arr_v, est = "PLANNED", None, None, planned_arr
                elif act_arr is not None and act_arr <= self.as_of:
                    status, act_dep_v, act_arr_v, est = "DELIVERED", act_dep, act_arr, act_arr
                else:
                    act_dep_v, act_arr_v = act_dep, None
                    est = est_arr if is_s2 else (act_arr if act_arr is not None else est_arr)
                    status = "DELAYED" if (est - planned_arr) > timedelta(hours=4) else "IN_TRANSIT"
                shp = {"shipment_id": sid, "from_location": lane["factory_id"], "to_location": lane["warehouse_id"],
                       "partner_id": lane["partner_id"], "planned_departure": dep, "actual_departure": act_dep_v,
                       "planned_arrival": planned_arr, "estimated_arrival": est, "actual_arrival": act_arr_v,
                       "status": status, "pallet_count": len(load),
                       "case_count": sum(p["case_count"] for p in load), "_pallets": load}
                for p in load:
                    p["shipment_id"] = sid
                    p["_shipment"] = shp
                    if status in ("IN_TRANSIT", "DELAYED"):
                        p["status"] = "DISPATCHED"
                    elif status == "DELIVERED":
                        p["status"] = "ARRIVED"
                    if act_dep_v is not None:
                        self.events.append(dict(object_uid=p["pallet_uid"], object_level="PALLET",
                                                event_type="DISPATCH", ts=act_dep_v,
                                                location_id=lane["factory_id"], source_system="WAREHOUSE_SYSTEM",
                                                child_count=p["case_count"], shipment_id=sid))
                    if act_arr_v is not None:
                        self.events.append(dict(object_uid=p["pallet_uid"], object_level="PALLET",
                                                event_type="ARRIVE", ts=act_arr_v,
                                                location_id=lane["warehouse_id"], source_system="WAREHOUSE_SYSTEM",
                                                child_count=p["case_count"], shipment_id=sid))
                shipments.append(shp)
        shipments.sort(key=lambda s: (s["planned_departure"], s["shipment_id"]))
        ids = [s["shipment_id"] for s in shipments]
        assert len(ids) == len(set(ids)), "duplicate shipment ids"
        self.shipments = shipments
        self.shipment_by_id = {s["shipment_id"]: s for s in shipments}
        # pack status follows its case's pallet
        for pk in self.packs:
            c = pk["_case"]
            if c is None:
                continue
            ps = c["_pallet"]["status"]
            pk["status"] = {"OPEN": "AGGREGATED", "READY": "AGGREGATED",
                            "DISPATCHED": "DISPATCHED", "ARRIVED": "ARRIVED"}[ps]

    # ---------------------------------------------------------------- authority submissions
    def build_submissions(self):
        subs = []
        s1_case_ids = {c["case_uid"] for c in self.s1_cases}
        for s in self.shipments:
            wh = self.warehouses[s["to_location"]]
            m = self.markets[wh["market_id"]]
            auth = self.authority_by_market[m["market_id"]]
            for stype in REQUIRED_SUBMISSIONS[m["regulation_profile"]]:
                ev = s["actual_departure"] if stype == "DISPATCH" else s["actual_arrival"]
                if ev is None:
                    continue
                sub_ts = ev + timedelta(minutes=self.r_misc.randint(4, 25))
                if sub_ts > self.as_of:
                    continue
                resp = sub_ts + timedelta(minutes=self.r_misc.randint(2, 35))
                s1_in = [c for p in s["_pallets"] for c in p["_cases"] if c["case_uid"] in s1_case_ids]
                row = {"shipment_id": s["shipment_id"], "authority_id": auth["authority_id"],
                       "submission_type": stype, "event_ts": ev, "submitted_ts": sub_ts,
                       "sla_due_ts": ev + timedelta(hours=auth["submission_sla_hours"]),
                       "status": "ACCEPTED", "response_ts": resp, "rejection_code": "", "rejection_reason": "",
                       "resubmission_of": "", "declared_pallets": s["pallet_count"],
                       "declared_cases": s["case_count"], "_s1": len(s1_in)}
                if s1_in and stype == "DISPATCH":
                    total = s["case_count"]
                    row["status"] = "REJECTED"
                    row["rejection_code"] = "MISSING_AGGREGATION_DATA"
                    row["rejection_reason"] = (
                        f"Missing aggregation data: {len(s1_in)} of {total} declared shipping cases contain fewer "
                        f"bundles than the declared product hierarchy (expected "
                        f"{self.products[s1_in[0]['sku']]['bundles_per_case']} bundles per case).")
                if resp > self.as_of:
                    row["status"], row["response_ts"] = "PENDING", None
                subs.append(row)
        # historical rejections that were corrected and resubmitted (background noise)
        older = [r for r in subs if r["status"] == "ACCEPTED" and r["submitted_ts"] < self.as_of - timedelta(days=6)]
        reasons = [("SCHEMA_VALIDATION", "Schema validation failed: event timestamp not in UTC format."),
                   ("DUPLICATE_MESSAGE", "Duplicate message identifier; message already processed."),
                   ("LATE_SUBMISSION", "Submission received after the statutory deadline.")]
        resubs = []
        for r, (code, text) in zip(self.r_misc.sample(older, 3), reasons):
            r["status"], r["rejection_code"], r["rejection_reason"] = "REJECTED", code, text
            new = dict(r)
            new.update({"submitted_ts": r["response_ts"] + timedelta(minutes=self.r_misc.randint(50, 240)),
                        "status": "ACCEPTED", "rejection_code": "", "rejection_reason": "", "_s1": 0})
            new["response_ts"] = new["submitted_ts"] + timedelta(minutes=self.r_misc.randint(3, 20))
            new["_resub_of"] = r
            resubs.append(new)
        subs.extend(resubs)
        subs.sort(key=lambda x: x["submitted_ts"])
        for i, r in enumerate(subs, start=1):
            r["submission_id"] = f"SUB-{i:06d}"
        for r in subs:
            if "_resub_of" in r:
                r["resubmission_of"] = r["_resub_of"]["submission_id"]
        self.submissions = subs

    # ---------------------------------------------------------------- inventory and demand
    def build_supply_chain(self):
        A = self.A
        forecast = []
        d = self.period_start
        fid = 0
        while d <= A + timedelta(days=FORECAST_DAYS_AHEAD - 1):
            for mkt, skus in MARKET_DEMAND.items():
                for sku in skus:
                    fid += 1
                    forecast.append({"forecast_id": f"FC-{d:%Y%m%d}-{mkt[4:]}-{sku}", "forecast_date": dstr(d),
                                     "market_id": mkt, "sku": sku,
                                     "forecast_qty": int(round(self.market_daily(mkt, sku, d))), "uom": "CASE"})
            d += timedelta(days=1)
        self.forecast = forecast

        pairs = [(w["warehouse_id"], sku) for w in WAREHOUSES for sku in MARKET_DEMAND[w["market_id"]]]
        snap_days = list(self.days())
        snap_time = {dd: at(dd, 6) for dd in snap_days}
        arrivals = defaultdict(list)    # (wh, sku) -> [(ts, cases)]
        departures = defaultdict(list)  # (wh, sku) -> [(dep_ts, arr_ts or None, cases)]
        for s in self.shipments:
            if s["actual_departure"] is None:
                continue
            per_sku = defaultdict(int)
            for p in s["_pallets"]:
                per_sku[p["sku"]] += p["case_count"]
            for sku, n in per_sku.items():
                departures[(s["to_location"], sku)].append((s["actual_departure"], s["actual_arrival"], n))
                if s["actual_arrival"] is not None:
                    arrivals[(s["to_location"], sku)].append((s["actual_arrival"], n))
        outflow = {}
        for wh, sku in pairs:
            for dd in snap_days:
                outflow[(wh, sku, dd)] = self.wh_daily(wh, sku, dd) * self.r_inv.uniform(0.9, 1.1)

        def fwd_daily(wh, sku):
            return sum(self.wh_daily(wh, sku, A + timedelta(days=k)) for k in range(7)) / 7.0

        targets = {}
        for wh, sku in pairs:
            targets[(wh, sku)] = self.r_inv.uniform(5.5, 12.0)
        targets[("WH-BET-D1", "SKU-03")] = 2.1
        targets[("WH-BET-D2", "SKU-03")] = 11.5

        snaps = []
        self.cover = {}
        for wh, sku in pairs:
            net = []
            for i, dd in enumerate(snap_days):
                t = snap_time[dd]
                arr = sum(n for (a_ts, n) in arrivals[(wh, sku)] if a_ts <= t)
                out = sum(outflow[(wh, sku, snap_days[j])] for j in range(i))
                net.append(arr - out)
            fd = fwd_daily(wh, sku)
            init_target = targets[(wh, sku)] * fd - net[-1]
            floor = 0.8 * fd
            init_min = max(0.0, max(floor - n for n in net))
            init = max(init_target, init_min)
            for i, dd in enumerate(snap_days):
                t = snap_time[dd]
                transit = sum(n for (dep, arr, n) in departures[(wh, sku)] if dep <= t and (arr is None or arr > t))
                snaps.append({"snapshot_id": f"INV-{dd:%Y%m%d}-{wh}-{sku}", "snapshot_date": dstr(dd),
                              "snapshot_ts": t, "warehouse_id": wh, "sku": sku,
                              "qty_on_hand": int(round(init + net[i])), "qty_in_transit": transit, "uom": "CASE"})
            self.cover[(wh, sku)] = (init + net[-1]) / fd
        self.inventory = snaps

    # ---------------------------------------------------------------- maintenance, telemetry, scans
    def build_maintenance(self):
        logs = []
        techs = ["J. Kowal", "A. Nowicki", "M. Dvorak", "P. Lis", "K. Novotna", "T. Wrona"]
        for ln in self.lines:
            for dd in self.days():
                if dd.weekday() == 6 and self.r_misc.chance(0.75):
                    logs.append({"line_id": ln["line_id"], "ts": at(dd, self.r_misc.randint(7, 12), 0),
                                 "maintenance_type": "PREVENTIVE", "component": "Line (weekly)",
                                 "description": "Weekly preventive maintenance: cleaning, lubrication, "
                                                "camera and printer calibration check.",
                                 "technician": self.r_misc.choice(techs),
                                 "downtime_minutes": 120})
        comps = [("Glue unit", "Glue nozzle blocked on carton wrapper; nozzle cleaned."),
                 ("Pack printer", "Code print contrast low; ribbon replaced."),
                 ("Bundle wrapper", "Film tension alarm; film roll re-threaded."),
                 ("Case erector", "Case erector jam cleared."),
                 ("Bundle aggregation scanner", "Short no-read burst; scanner window wiped, read rate normal.")]
        active = {(o["line_id"], o["start_ts"].date()): o for o in self.orders}
        for (lid, dd), o in sorted(active.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if (lid, dd) == (self.s1_line, self.s1_day):
                continue
            if self.r_misc.chance(0.05):
                comp, desc = self.r_misc.choice(comps)
                t = o["start_ts"] + timedelta(minutes=self.r_misc.randint(30, 400))
                if t > self.as_of:
                    continue
                logs.append({"line_id": lid, "ts": t, "maintenance_type": "CORRECTIVE", "component": comp,
                             "description": desc, "technician": self.r_misc.choice(techs),
                             "downtime_minutes": self.r_misc.randint(5, 25)})
        logs.append({"line_id": self.maint_line, "ts": at(self.maint_from, 5),
                     "maintenance_type": "PLANNED_OVERHAUL", "component": "Line (overhaul)",
                     "description": f"Planned overhaul of the heated-stick line. Line out of production until "
                                    f"{dstr(self.maint_to)}.",
                     "technician": "Contractor team", "downtime_minutes": 0})
        logs.append({"line_id": self.s1_line, "ts": self.s1_fault_ts, "maintenance_type": "SCANNER_FAULT",
                     "component": "Case aggregation scanner (camera 2)",
                     "description": "Operator reports intermittent no-reads at the case aggregation station; "
                                    "lens contamination or misalignment suspected. Technician requested.",
                     "technician": "Shift operator", "downtime_minutes": 0})
        logs.append({"line_id": self.s1_line, "ts": self.s1_bypass_ts, "maintenance_type": "OPERATING_MODE_CHANGE",
                     "component": "Case aggregation scanner (camera 2)",
                     "description": "Case aggregation station switched to bypass mode (no line stop on missing "
                                    "bundle reads) to keep the line running until the technician arrives.",
                     "technician": "Shift lead", "downtime_minutes": 0})
        logs.append({"line_id": self.s1_line, "ts": self.s1_repair_ts, "maintenance_type": "REPAIR",
                     "component": "Case aggregation scanner (camera 2)",
                     "description": "Camera 2 lens cleaned and realigned, read rate back to 99.9%. "
                                    "Bypass mode disabled. Cases aggregated in bypass mode were not re-checked.",
                     "technician": "A. Nowicki", "downtime_minutes": 0})
        logs = [l for l in logs if l["ts"] <= self.as_of]
        logs.sort(key=lambda x: (x["ts"], x["line_id"]))
        for i, l in enumerate(logs, start=1):
            l["log_id"] = f"MNT-{i:05d}"
        self.maintenance = logs

    def build_telemetry(self):
        rows = []
        runs = defaultdict(list)
        for o in self.orders:
            end = self.as_of if o["status"] == "IN_PROGRESS" else o["_actual_end"]
            runs[o["line_id"]].append((o["start_ts"], end, o))
        t = self.telemetry_start
        blips = set()
        for ln in self.lines:
            for _ in range(2):
                k = self.r_tel.randint(0, TELEMETRY_HOURS * 12 - 3)
                blips.add((ln["line_id"], k))
                blips.add((ln["line_id"], k + 1))
        k = 0
        n = 0
        while t < self.as_of:
            for ln in self.lines:
                lid = ln["line_id"]
                active = None
                for (st, en, o) in runs[lid]:
                    if st <= t < en:
                        active = o
                        break
                for station in ("BUNDLE_AGGREGATION", "CASE_AGGREGATION"):
                    n += 1
                    row = {"telemetry_id": f"TEL-{n:07d}", "line_id": lid, "station": station, "ts": t,
                           "codes_expected": 0, "codes_read": 0, "no_reads": 0, "read_rate_pct": "",
                           "scanner_status": "IDLE", "station_mode": "NORMAL"}
                    if active is not None:
                        p = self.products[active["sku"]]
                        per5 = ln["rated_cases_per_hour"] / 12.0
                        expected = per5 * (p["packs_per_bundle"] * p["bundles_per_case"]
                                           if station == "BUNDLE_AGGREGATION" else p["bundles_per_case"])
                        expected = max(1, int(round(expected * self.r_tel.uniform(0.9, 1.05))))
                        rr = min(100.0, self.r_tel.gauss(99.86, 0.07))
                        status = "OK"
                        mode = "NORMAL"
                        if (lid, k) in blips:
                            rr = self.r_tel.uniform(97.2, 97.9)
                        if (lid == self.s1_line and station == "CASE_AGGREGATION"
                                and self.s1_fault_ts - timedelta(minutes=5) <= t < self.s1_repair_ts):
                            rr = max(80.0, min(96.5, self.r_tel.gauss(92.0, 1.8)))
                            status = "DEGRADED"
                            if t >= self.s1_bypass_ts:
                                mode = "BYPASS"
                        if rr < 98.0 and status == "OK":
                            status = "DEGRADED"
                        read = int(round(expected * rr / 100.0))
                        row.update({"codes_expected": expected, "codes_read": read, "no_reads": expected - read,
                                    "read_rate_pct": round(rr, 2), "scanner_status": status, "station_mode": mode})
                    rows.append(row)
            t += timedelta(minutes=5)
            k += 1
        self.telemetry = rows

    def build_consumer_scans(self):
        scans = []
        arrived = [p for p in self.packs if p["status"] == "ARRIVED"]
        s4 = self.facts["s4_pack"]
        candidates = []
        for p in arrived:
            arr = p["_case"]["_pallet"]["_shipment"]["actual_arrival"]
            if arr + timedelta(hours=18) < self.as_of - timedelta(hours=1) and p["pack_uid"] != s4["pack_uid"]:
                candidates.append((p, arr))
        chosen = self.r_scan.sample(candidates, min(900, len(candidates)))
        for p, arr in chosen:
            span = (self.as_of - arr - timedelta(hours=18)).total_seconds()
            t = arr + timedelta(hours=18) + timedelta(seconds=int(self.r_scan.random() * span))
            mkt = self.markets[self.warehouses[p["_case"]["_pallet"]["destination_warehouse_id"]]["market_id"]]
            cc = mkt["country_code"]
            scans.append({"pack_uid": p["pack_uid"], "ts": t, "country_code": cc,
                          "city": self.r_scan.choice(CONSUMER_CITIES[cc]), "result": "VALID",
                          "distance_from_previous_scan_km": ""})
        # S6: same pack scanned in two distant countries within 24 hours
        beta = [(p, a) for p, a in candidates
                if p["_case"]["_pallet"]["destination_warehouse_id"].startswith("WH-BET")
                and p["pack_uid"] not in {s["pack_uid"] for s in scans}]
        s6_pack, _ = beta[len(beta) // 3]
        t1 = self.as_of - timedelta(hours=22, minutes=14)
        t2 = t1 + timedelta(hours=13, minutes=37)
        scans.append({"pack_uid": s6_pack["pack_uid"], "ts": t1, "country_code": "XB", "city": "Beta City",
                      "result": "VALID", "distance_from_previous_scan_km": ""})
        scans.append({"pack_uid": s6_pack["pack_uid"], "ts": t2, "country_code": "XZ", "city": "Port Zephyr",
                      "result": "DUPLICATE", "distance_from_previous_scan_km": 8940})
        self.facts["s6"] = {"pack_uid": s6_pack["pack_uid"], "t1": t1, "t2": t2}
        # codes that do not exist in the system (counterfeit suspicion)
        for _ in range(14):
            fake = f"PK-{self.r_scan.choice(['PL-01', 'PL-02', 'CZ-01'])}-{self.r_scan.code(8)}"
            while fake in self.used_uids:
                fake = f"PK-PL-02-{self.r_scan.code(8)}"
            cc = self.r_scan.choice(["XA", "XB", "XC", "XD"])
            t = self.as_of - timedelta(seconds=int(self.r_scan.random() * 4 * 86400))
            scans.append({"pack_uid": fake, "ts": t, "country_code": cc,
                          "city": self.r_scan.choice(CONSUMER_CITIES[cc]), "result": "UNKNOWN",
                          "distance_from_previous_scan_km": ""})
        scans.sort(key=lambda s: s["ts"])
        for i, s in enumerate(scans, start=1):
            s["scan_id"] = f"SCN-{i:06d}"
            if s["result"] in ("VALID", "DUPLICATE"):
                self.events.append(dict(object_uid=s["pack_uid"], object_level="PACK", event_type="SCAN_CONSUMER",
                                        ts=s["ts"], location_id=s["country_code"], source_system="CONSUMER_APP",
                                        child_count="", shipment_id=""))
        self.scans = scans

    # ---------------------------------------------------------------- scenario facts
    def collect_facts(self):
        f = self.facts
        s1_order = next(o for o in self.orders if o["line_id"] == self.s1_line and o["start_ts"].date() == self.s1_day)
        s1_ships = sorted({c["_pallet"]["shipment_id"] for c in self.s1_cases if c["_pallet"]["shipment_id"]})
        orphan_bundles = [b for b in self.bundles if b["status"] == "NOT_AGGREGATED"]
        f["s1"] = {"line_id": self.s1_line, "day": self.s1_day, "order": s1_order, "cases": self.s1_cases,
                   "first_case_ts": min(c["created_ts"] for c in self.s1_cases),
                   "last_case_ts": max(c["created_ts"] for c in self.s1_cases),
                   "orphan_bundles": len(orphan_bundles),
                   "orphan_packs": sum(b["pack_count"] for b in orphan_bundles),
                   "shipments": s1_ships, "fault_ts": self.s1_fault_ts, "bypass_ts": self.s1_bypass_ts,
                   "repair_ts": self.s1_repair_ts,
                   "sku": s1_order["sku"]}
        s2 = next(s for s in self.shipments if (s["from_location"], s["to_location"]) == self.s2_lane
                  and s["planned_departure"] == self.s2_planned_departure)
        s2_packs = sum(p["case_count"] * self.products[p["sku"]]["packs_per_case"] for p in s2["_pallets"])
        s2_by_sku = defaultdict(lambda: [0, 0])
        for p in s2["_pallets"]:
            s2_by_sku[p["sku"]][0] += 1
            s2_by_sku[p["sku"]][1] += p["case_count"]
        f["s2"] = {"shipment": s2, "packs": s2_packs, "by_sku": dict(s2_by_sku),
                   "delay_h": (s2["actual_departure"] - s2["planned_departure"]).total_seconds() / 3600}
        rej = [r for r in self.submissions if r["rejection_code"] == "MISSING_AGGREGATION_DATA"]
        f["s3"] = {"submissions": rej}
        # S4: a clean pack on the first pallet of the S4 order delivered to a Beta distributor
        s4_order_id = f"PO-{self.A - timedelta(days=5):%Y%m%d}-PL01L1"
        cands = [p for p in self.packs if p["order_id"] == s4_order_id and p["status"] == "ARRIVED"]
        s4 = cands[len(cands) // 7]
        case = s4["_case"]
        pallet = case["_pallet"]
        f["s4_pack"] = s4
        f["s4"] = {"pack": s4, "bundle_uid": s4["bundle_uid"], "case": case, "pallet": pallet,
                   "shipment": pallet["_shipment"], "warehouse": self.warehouses[pallet["destination_warehouse_id"]]}
        f["s5"] = {"d1": self.cover[("WH-BET-D1", "SKU-03")], "d2": self.cover[("WH-BET-D2", "SKU-03")],
                   "d1_row": next(r for r in self.inventory if r["warehouse_id"] == "WH-BET-D1"
                                  and r["sku"] == "SKU-03" and r["snapshot_date"] == dstr(self.A)),
                   "d2_row": next(r for r in self.inventory if r["warehouse_id"] == "WH-BET-D2"
                                  and r["sku"] == "SKU-03" and r["snapshot_date"] == dstr(self.A)),
                   "d1_daily": sum(self.wh_daily("WH-BET-D1", "SKU-03", self.A + timedelta(days=k))
                                   for k in range(7)) / 7,
                   "d2_daily": sum(self.wh_daily("WH-BET-D2", "SKU-03", self.A + timedelta(days=k))
                                   for k in range(7)) / 7}

    # ---------------------------------------------------------------- run
    def run(self):
        self.plan_production()
        self.build_units()
        self.build_shipments()
        self.build_submissions()
        self.build_supply_chain()
        self.build_maintenance()
        self.collect_facts()
        self.build_consumer_scans()
        self.build_telemetry()
        self.events.sort(key=lambda e: (e["ts"], e["object_level"] != "PACK", e["object_uid"]))
        for i, e in enumerate(self.events, start=1):
            e["event_id"] = f"EV-{i:09d}"


# --------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------
def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        return ts(v)
    if v is None:
        return ""
    return v


def write_csv(path: str, columns: list[str], rows: list[dict]) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in columns])
    return len(rows)


def write_csv_parts(folder: str, columns: list[str], rows: list[dict]) -> list[tuple[str, int]]:
    os.makedirs(folder, exist_ok=True)
    parts, buf, size, idx = [], [], 0, 1
    header = ",".join(columns) + "\n"

    def flush():
        nonlocal buf, size, idx
        if not buf:
            return
        name = f"part-{idx:03d}.csv"
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="") as fh:
            fh.write(header)
            fh.write("".join(buf))
        parts.append((name, len(buf)))
        buf, size, idx = [], 0, idx + 1

    for r in rows:
        s = io.StringIO()
        csv.writer(s, lineterminator="\n").writerow([fmt(r.get(c)) for c in columns])
        line = s.getvalue()
        if size + len(line) + len(header) > PART_MAX_BYTES:
            flush()
        buf.append(line)
        size += len(line)
    flush()
    return parts


COLUMNS = {
    "factory": ["factory_id", "name", "country_code", "timezone"],
    "production_line": ["line_id", "factory_id", "line_name", "line_type", "status", "rated_cases_per_hour",
                        "aggregation_scanner_model", "commissioned_date"],
    "product": ["sku", "brand_name", "product_name", "category", "packs_per_bundle", "bundles_per_case",
                "cases_per_pallet", "packs_per_case", "packs_per_pallet", "sticks_per_pack"],
    "market": ["market_id", "name", "country_code", "regulation_profile", "requires_stamp"],
    "tax_authority": ["authority_id", "market_id", "name", "submission_sla_hours", "contact_email"],
    "warehouse": ["warehouse_id", "name", "market_id", "warehouse_type", "demand_share_pct", "operator_partner_id"],
    "partner": ["partner_id", "name", "partner_type", "contact_email"],
    "production_order": ["order_id", "line_id", "sku", "target_market_id", "destination_warehouse_id",
                         "planned_qty", "produced_qty", "uom", "start_ts", "end_ts", "status"],
    "pack": ["pack_uid", "sku", "order_id", "line_id", "bundle_uid", "commissioned_ts", "status"],
    "bundle": ["bundle_uid", "case_uid", "line_id", "order_id", "sku", "created_ts", "pack_count", "status"],
    "shipping_case": ["case_uid", "pallet_uid", "line_id", "order_id", "sku", "created_ts",
                      "expected_bundle_count", "bundle_count", "aggregation_status"],
    "pallet": ["pallet_uid", "shipment_id", "line_id", "order_id", "sku", "destination_warehouse_id",
               "created_ts", "closed_ts", "case_count", "status"],
    "shipment": ["shipment_id", "from_location", "to_location", "partner_id", "planned_departure",
                 "actual_departure", "planned_arrival", "estimated_arrival", "actual_arrival", "status",
                 "pallet_count", "case_count"],
    "authority_submission": ["submission_id", "shipment_id", "authority_id", "submission_type", "event_ts",
                             "submitted_ts", "sla_due_ts", "status", "response_ts", "rejection_code",
                             "rejection_reason", "resubmission_of", "declared_pallets", "declared_cases"],
    "inventory_snapshot": ["snapshot_id", "snapshot_date", "snapshot_ts", "warehouse_id", "sku", "qty_on_hand",
                           "qty_in_transit", "uom"],
    "demand_forecast": ["forecast_id", "forecast_date", "market_id", "sku", "forecast_qty", "uom"],
    "maintenance_log": ["log_id", "line_id", "ts", "maintenance_type", "component", "description", "technician",
                        "downtime_minutes"],
    "consumer_scan": ["scan_id", "pack_uid", "ts", "country_code", "city", "result",
                      "distance_from_previous_scan_km"],
    "trace_event": ["event_id", "object_uid", "object_level", "event_type", "ts", "location_id", "source_system",
                    "child_count", "shipment_id"],
    "line_scanner_telemetry": ["telemetry_id", "line_id", "station", "ts", "codes_expected", "codes_read",
                               "no_reads", "read_rate_pct", "scanner_status", "station_mode"],
    "production_line_daily": ["production_date", "factory_id", "line_id", "order_id", "sku", "target_market_id",
                              "planned_packs", "packs_commissioned", "packs_decommissioned", "bundles_aggregated",
                              "cases_aggregated", "cases_with_mismatch", "pallets_built"],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--out", default=os.path.dirname(here), help="output folder (default: parent of generator/)")
    ap.add_argument("--as-of", default=DEFAULT_AS_OF, help="data snapshot time, a Wednesday, ISO-8601 UTC")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()
    as_of = datetime.strptime(args.as_of, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

    g = Generator(as_of, args.seed)
    g.run()

    out = args.out
    for sub in ("lakehouse", "eventhouse", "semantic-model", "notebooks", "work-context"):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)

    counts = {}
    lh = os.path.join(out, "lakehouse")
    counts["factory"] = write_csv(f"{lh}/factory.csv", COLUMNS["factory"], FACTORIES)
    counts["production_line"] = write_csv(f"{lh}/production_line.csv", COLUMNS["production_line"], g.lines)
    counts["product"] = write_csv(f"{lh}/product.csv", COLUMNS["product"], list(g.products.values()))
    counts["market"] = write_csv(f"{lh}/market.csv", COLUMNS["market"], MARKETS)
    counts["tax_authority"] = write_csv(f"{lh}/tax_authority.csv", COLUMNS["tax_authority"], TAX_AUTHORITIES)
    counts["warehouse"] = write_csv(f"{lh}/warehouse.csv", COLUMNS["warehouse"], WAREHOUSES)
    counts["partner"] = write_csv(f"{lh}/partner.csv", COLUMNS["partner"], PARTNERS)
    counts["production_order"] = write_csv(f"{lh}/production_order.csv", COLUMNS["production_order"], g.orders)
    pack_rows = sorted(g.packs, key=lambda p: p["commissioned_ts"])
    pack_parts = write_csv_parts(f"{lh}/pack", COLUMNS["pack"], pack_rows)
    counts["pack"] = len(pack_rows)
    counts["bundle"] = write_csv(f"{lh}/bundle.csv", COLUMNS["bundle"],
                                 sorted(g.bundles, key=lambda b: b["created_ts"]))
    counts["shipping_case"] = write_csv(f"{lh}/shipping_case.csv", COLUMNS["shipping_case"], g.cases)
    counts["pallet"] = write_csv(f"{lh}/pallet.csv", COLUMNS["pallet"], g.pallets)
    counts["shipment"] = write_csv(f"{lh}/shipment.csv", COLUMNS["shipment"], g.shipments)
    counts["authority_submission"] = write_csv(f"{lh}/authority_submission.csv",
                                               COLUMNS["authority_submission"], g.submissions)
    counts["inventory_snapshot"] = write_csv(f"{lh}/inventory_snapshot.csv", COLUMNS["inventory_snapshot"],
                                             g.inventory)
    counts["demand_forecast"] = write_csv(f"{lh}/demand_forecast.csv", COLUMNS["demand_forecast"], g.forecast)
    counts["maintenance_log"] = write_csv(f"{lh}/maintenance_log.csv", COLUMNS["maintenance_log"], g.maintenance)
    counts["consumer_scan"] = write_csv(f"{lh}/consumer_scan.csv", COLUMNS["consumer_scan"], g.scans)

    eh = os.path.join(out, "eventhouse")
    trace_parts = write_csv_parts(f"{eh}/trace_event", COLUMNS["trace_event"], g.events)
    counts["trace_event"] = len(g.events)
    counts["line_scanner_telemetry"] = write_csv(f"{eh}/line_scanner_telemetry.csv",
                                                 COLUMNS["line_scanner_telemetry"], g.telemetry)
    counts["production_line_daily"] = write_csv(f"{out}/semantic-model/production_line_daily.csv",
                                                COLUMNS["production_line_daily"], g.kpis)

    g.facts["pack_parts"] = pack_parts
    work_context.write_all(g, os.path.join(out, "work-context"))
    docs_templates.write_notebook(g, os.path.join(out, "notebooks", "create_semantic_model.ipynb"),
                                  COLUMNS["production_line_daily"])
    docs_templates.write_readme_data(g, os.path.join(out, "README_data.md"), counts,
                                     {"pack": pack_parts, "trace_event": trace_parts})
    docs_templates.write_tutorial_guide(g, os.path.join(out, "TUTORIAL_GUIDE.md"))
    docs_templates.write_folder_readme(g, os.path.join(out, "README.md"))
    print(json.dumps({"as_of": ts(as_of), "seed": args.seed, "rows": counts,
                      "pack_parts": len(pack_parts), "trace_event_parts": len(trace_parts)}, indent=1))


if __name__ == "__main__":
    main()
