"""Unstructured 'work context' for the demo (Work IQ side): emails, Teams messages and SOPs.

All people, companies, domains and messages are fictional. The relevant items quote the IDs
of the seeded scenarios, so they always match the generated data.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

UTC = timezone.utc
ME = ("Marta K.", "marta.k@ttdemo.example")


def _t(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hm(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")


def build_emails(g) -> list[dict]:
    f = g.facts
    A = g.as_of
    s1, s2, s3, s4, s5 = f["s1"], f["s2"], f["s3"], f["s4"], f["s5"]
    shp2 = s2["shipment"]
    sub_a, sub_b = s3["submissions"]
    d1_row, d2_row = s5["d1_row"], s5["d2_row"]
    yday = s1["day"].strftime("%d %b")
    sla_gamma = g.authority_by_market["MKT-GAMMA"]["submission_sla_hours"]
    mails = []

    def add(sender, to, subject, sent, body, relevant, scenario=""):
        mails.append({"from_name": sender[0], "from": sender[1], "to": to, "subject": subject,
                      "sent": sent, "body": body.strip() + "\n", "relevant": relevant, "scenario": scenario})

    # ---------------- relevant
    add(("Tomasz W. (Shift Lead, Factory PL-02)", "tomasz.w@ttdemo.example"),
        "pl02-production@ttdemo.example, t-and-t-ops@ttdemo.example",
        "PL-02 Line 3 - case aggregation scanner in bypass mode",
        s1["bypass_ts"] + timedelta(minutes=9),
        f"""Hi all,

FYI for shift A on {yday}: the case aggregation scanner (camera 2) on PL-02 Line 3 has intermittent
no-reads since about 06:20 UTC. To avoid stopping the line we switched the station to bypass mode at
06:38 UTC (no stop on missing bundle reads). A maintenance ticket is logged and a technician is booked
for the afternoon.

Running order {s1['order']['order_id']} ({s1['sku']} for Market Gamma).

Regards,
Tomasz W.
Shift Lead, Factory PL-02""", True, "S1")

    for sub in (sub_a, sub_b):
        add(("Gamma Customs and Excise Agency", "no-reply@excise-gamma.example.test"), ME[1],
            f"Submission {sub['submission_id']} rejected - MISSING_AGGREGATION_DATA",
            sub["response_ts"] + timedelta(minutes=1),
            f"""This is an automated message.

Your dispatch notification {sub['submission_id']} for shipment {sub['shipment_id']} was REJECTED.

Reason code: MISSING_AGGREGATION_DATA
Detail: {sub['rejection_reason']}

Submit a corrected notification within the service level of {sla_gamma} hours of the dispatch event.
Do not reply to this message.""", True, "S3")

    add(("Northgate Haulage - Dispatch", "ops.northgate@example-logistics.test"), ME[1],
        f"Delay notice - {shp2['shipment_id']} - revised ETA",
        A - timedelta(minutes=8),
        f"""Dear Marta,

Update on shipment {shp2['shipment_id']} (Factory PL-01 to Beta North Distributor, {shp2['pallet_count']} pallets):

- Planned departure: {_hm(shp2['planned_departure'])}
- Actual departure:  {_hm(shp2['actual_departure'])} (26 hours late - tractor unit breakdown, replacement truck)
- Planned arrival:   {_hm(shp2['planned_arrival'])}
- Revised ETA:       {_hm(shp2['estimated_arrival'])} (includes about 4 hours queue at the border crossing)

We apologise for the delay and will confirm when the truck is unloaded.

Kind regards,
Dispatch team
Northgate Haulage""", True, "S2")

    add(("Beta Revenue and Stamp Office - Trace Requests", "trace-requests@revenue-beta.example.test"), ME[1],
        f"Request for trace information - pack {s4['pack']['pack_uid']}",
        A - timedelta(hours=14, minutes=40),
        f"""Dear Sir or Madam,

During a routine retail inspection in Market Beta on {yday}, our inspectors recorded the pack with
unique identifier {s4['pack']['pack_uid']} ({g.products[s4['pack']['sku']]['product_name']}).

In accordance with the reporting obligations for Market Beta, please provide the full trace of this
pack: production site and line, date and time of commissioning, the aggregation hierarchy (bundle,
shipping case, pallet), the shipment with its dispatch and arrival times, and the receiving distributor.

Please respond within two business days, quoting reference BRS-TR-{A:%Y}-0417.

Yours faithfully,
Trace Requests Desk
Beta Revenue and Stamp Office""", True, "S4")

    add(("Beta Operations - Meridian 3PL Services", "beta.ops.meridian@example-logistics.test"), ME[1],
        "Beta warehouses - stock note and transfer slots this week",
        A - timedelta(hours=16, minutes=5),
        f"""Hi Marta,

Short operational note for the two Beta warehouses we run for you:

- Beta North Distributor (WH-BET-D1): Orion Red (SKU-03) is getting thin this week. The next inbound
  is the Northgate truck from PL-01.
- Beta South Distributor (WH-BET-D2): comfortable on Orion Red.
- We have a free shuttle slot between South and North on Wednesday afternoon and Thursday morning if you
  need a stock transfer (up to 6 pallets, same-day delivery).

Best regards,
Beta Operations, Meridian 3PL Services""", True, "S5")

    add(("Elena V. (Compliance, Track & Trace)", "elena.v@ttdemo.example"), ME[1],
        "Gamma rejections from yesterday - please check aggregation",
        A - timedelta(minutes=26),
        f"""Morning Marta,

Gamma rejected two of our dispatch notifications yesterday, {sub_a['submission_id']} and {sub_b['submission_id']}, both with
MISSING_AGGREGATION_DATA. Both shipments left PL-02. Their SLA is only {sla_gamma} hours, so we are already in
breach on both.

Can you check what happened with the aggregation on the PL-02 side and confirm when we can send corrected
files? I need to inform the Gamma account team before noon.

Thanks,
Elena""", True, "S3")

    # ---------------- noise
    noise = [
        (("IT Service Desk", "servicedesk@ttdemo.example"), "Planned maintenance: VPN gateway, Saturday 22:00-02:00",
         -60, "The VPN gateway is updated on Saturday night. Expect short interruptions. No action needed."),
        (("Canteen Krakow Office", "canteen@ttdemo.example"), "This week's lunch menu",
         -45, "Monday: vegetable soup. Tuesday: pierogi. Wednesday: pasta bar. Thursday: chef's special. Friday: fish."),
        (("HR Learning", "learning@ttdemo.example"), "Reminder: complete your annual data-privacy training",
         -40, "Your annual data-privacy e-learning is due by the end of the month. It takes about 25 minutes."),
        (("Supply Chain Digest", "newsletter@scdigest.example.test"), "Supply Chain Digest - weekly edition",
         -38, "This week: warehouse automation trends, port congestion index, and five tips for S&OP meetings."),
        (("Travel Desk", "travel@ttdemo.example"), "Booking confirmation - Krakow hotel",
         -36, "Your hotel booking for the regional workshop is confirmed. Check-in from 15:00."),
        (("Facility Management", "facilities@ttdemo.example"), "Fire drill on Thursday at 10:30",
         -34, "A fire drill takes place on Thursday at 10:30. Please follow the wardens' instructions."),
        (("Finance Shared Services", "expenses@ttdemo.example"), "Expense report reminder",
         -30, "You have two open expense items older than 30 days. Please submit them in the expense tool."),
        (("Ana P.", "ana.p@ttdemo.example"), "Team lunch on Friday?",
         -28, "Shall we do lunch on Friday to celebrate the quarter? Reply by Wednesday."),
        (("PL-01 Maintenance", "pl01-maintenance@ttdemo.example"), "PL-01 Line 1 - weekly preventive maintenance done",
         -26, "Weekly preventive maintenance on PL-01 Line 1 completed as planned. No findings."),
        (("Vistaline Freight - Accounts", "accounts.vistaline@example-logistics.test"), "Invoice VF-88213 for October",
         -24, "Please find our invoice for October line-haul services in the supplier portal. Payment terms 45 days."),
        (("Software Licensing", "licensing@ttdemo.example"), "License renewal: diagram tool",
         -22, "Your diagram tool license renews automatically next month. No action needed."),
        (("Internal Comms", "news@ttdemo.example"), "Town hall recording now available",
         -20, "The recording of last week's town hall is available on the intranet."),
        (("Security Awareness", "security@ttdemo.example"), "Phishing simulation results for your department",
         -19, "Thank you for taking part in last month's phishing simulation. Your department scored above average."),
        (("Parking Office", "parking@ttdemo.example"), "Car park level -2 closed on Saturday",
         -18, "Level -2 of the car park is closed on Saturday for line painting."),
        (("Data Platform Team", "dataplatform@ttdemo.example"), "Monthly data platform newsletter",
         -12, "New dashboards for warehouse throughput are live. Office hours every Thursday."),
        (("Survey Team", "survey@ttdemo.example"), "Quarterly engagement survey closes Friday",
         -10, "The quarterly engagement survey closes on Friday. It takes 10 minutes."),
        (("Office Services", "office@ttdemo.example"), "New printer on floor 3",
         -6, "A new multifunction printer is installed on floor 3 next to the kitchen."),
        (("Clearpath Customs Brokers", "desk.clearpath@example-logistics.test"), "Holiday opening hours",
         -4, "Our customs desk has reduced opening hours on public holidays in December. Plan your clearances early."),
        (("Lukas H.", "lukas.h@ttdemo.example"), "Slides for next week's process review",
         -2, "Here is the link to the draft slides for next week's process review. No rush - comments by Monday."),
    ]
    for sender, subject, hours, body in noise:
        add(sender, ME[1], subject, A + timedelta(hours=hours, minutes=7),
            f"Hello,\n\n{body}\n\nBest regards,\n{sender[0]}", False)
    mails.sort(key=lambda m: m["sent"])
    for i, m in enumerate(mails, start=1):
        m["email_id"] = f"EML-{i:03d}"
    return mails


def build_teams(g) -> list[dict]:
    d = g.facts["s1"]["day"]
    base = datetime(d.year, d.month, d.day, tzinfo=UTC)
    msgs = [
        (-1, 20, 55, "Kasia L.", "Handover shift B to night: all four lines ran to plan. L4 film roll changed at 18:10."),
        (-1, 21, 5, "Marek S.", "Thanks. No production tonight, only cleaning on L2."),
        (0, 5, 2, "Tomasz W.", "Shift A started. L1, L2, L3, L4 running. L3 on Nova Gold for Gamma today."),
        (0, 5, 40, "Kasia L.", "Reminder: the Gamma trucks leave 13:30 and 21:30 UTC as usual."),
        (0, 6, 24, "Tomasz W.", "L3 case scanner throwing no-reads again. Logged it with maintenance."),
        (0, 9, 15, "Piotr N.", "L1 glue level topped up, no stop."),
        (0, 13, 5, "Tomasz W.", "Handover shift A to B: L3 case scanner still flaky, the station is in bypass so "
                                "the line keeps running. Maintenance says they come after 18:00. Please keep an eye on it."),
        (0, 13, 20, "Anna B.", "Got it, taking over. Gamma truck loading now."),
        (0, 16, 2, "Anna B.", "L2 short stop (7 min) for a case erector jam, cleared."),
        (0, 18, 47, "Anna B.", "Technician fixed the L3 camera, read rate back to normal, bypass off."),
        (0, 21, 3, "Anna B.", "Handover shift B to night: all lines stopped to plan. Second Gamma truck at 21:30."),
        (0, 21, 55, "Marek S.", "Second Gamma truck left. Night cleaning on L4."),
        (1, 5, 1, "Tomasz W.", "Shift A started. All four lines running."),
        (1, 5, 30, "Kasia L.", "Coffee machine in the line office is fixed, finally."),
        (1, 6, 40, "Tomasz W.", "Does anyone know if the Gamma submissions went through yesterday? I haven't seen confirmations."),
    ]
    out = []
    for i, (dd, hh, mm, who, text) in enumerate(msgs, start=1):
        t = base + timedelta(days=dd, hours=hh, minutes=mm)
        if t > g.as_of:
            continue
        rel = "L3" in text and ("scanner" in text or "camera" in text)
        out.append({"message_id": f"TMS-{i:03d}", "team": "Factory PL-02", "channel": "Shift Handover",
                    "from": who, "sent": _t(t), "text": text, "relevant": rel, "scenario": "S1" if rel else ""})
    return out


SOP_AGGREGATION = """# SOP-TT-014: Handling aggregation mismatches

*Fictional procedure for the Track & Trace demo. It isn't a real company procedure.*

**Owner:** Track & Trace Operations
**Applies to:** all factories and production lines with unit-level serialization

## 1. Purpose

An aggregation mismatch means the recorded parent-child hierarchy doesn't match the physical
packaging. For example, a shipping case physically holds 5 bundles, but only 3 or 4 bundles are
aggregated to it in the system. Mismatches cause rejected authority submissions and break the trace
from pack to market.

## 2. Detection

Suspect a mismatch when any of these is true:

1. A shipping case has a `bundle_count` lower than the product's `bundles_per_case`.
2. Bundles have the status `NOT_AGGREGATED` (no parent case) more than 30 minutes after they were created.
3. A case aggregation scanner reports a read rate below 98% for more than 15 minutes, or the station runs
   in `BYPASS` mode.
4. An authority rejects a submission with the reason `MISSING_AGGREGATION_DATA`.

## 3. Immediate actions (within 1 hour)

1. Identify the line, production order and time window affected (first and last mismatched case).
2. Check the maintenance log and the scanner telemetry for the line in the same window.
3. Stop further dispatch of affected pallets that are still at the factory.
4. For affected pallets already dispatched, list the shipments and the authority submissions concerned.
5. Open an incident (priority P2, or P1 if a submission SLA is already breached) and inform Compliance.

## 4. Correction

1. Re-scan the affected cases, at the factory or at the receiving warehouse if they've already shipped.
2. Re-aggregate the orphan bundles into their physical cases (`DISAGGREGATE` and `AGGREGATE` events).
3. Send corrected submissions to the authority within its SLA.
4. Disable bypass mode only after the scanner read rate has been at least 99.5% for 30 minutes.

## 5. Prevention

- Bypass mode on an aggregation station needs shift lead approval and sends an automatic alert to
  Track & Trace Operations.
- Review the aggregation KPIs (Aggregation Error Rate %) in the morning briefing.
"""

SOP_TRACE = """# SOP-TT-021: Responding to authority trace requests

*Fictional procedure for the Track & Trace demo. It isn't a real company procedure.*

**Owner:** Track & Trace Operations, with Compliance
**Applies to:** all markets

## 1. Purpose

Tax authorities can ask for the full trace of a pack, for example after a retail inspection. The
answer must be complete, correct and on time.

## 2. Service levels

| Request type | Response time |
|---|---|
| Standard | 2 business days |
| Urgent (marked by the authority) | 1 business day |

## 3. Steps

1. Log the request: authority, reference, pack UID and due date.
2. Retrieve the full hierarchy: pack, bundle, shipping case, pallet, shipment and receiving warehouse.
3. Add the production details: factory, line, production order and commissioning time.
4. Add the logistics details: dispatch and arrival times, carrier, and the authority submissions for the
   shipment with their status.
5. Check that the chain is clean: no aggregation mismatches, no disaggregation without re-aggregation and
   no duplicate consumer scans for the UID. Flag anything unusual to Compliance before you send.
6. Draft the response with the template below and send it after Compliance has reviewed it.

## 4. Response template

> Reference: <authority reference>
> Pack <UID>, product <name>, commissioned at <factory>/<line> on <date time UTC> under order <order>.
> Aggregated into bundle <UID>, shipping case <UID> and pallet <UID>.
> Dispatched on <date time> with shipment <ID> (carrier <name>) and received by <warehouse> on <date time>.
> Your office accepted the dispatch and arrival notifications <IDs>.
"""


def write_all(g, folder: str) -> dict:
    os.makedirs(os.path.join(folder, "emails"), exist_ok=True)
    os.makedirs(os.path.join(folder, "sop"), exist_ok=True)
    mails = build_emails(g)
    for m in mails:
        msg = EmailMessage()
        msg["Message-ID"] = f"<{m['email_id'].lower()}@ttdemo.example>"
        msg["Date"] = format_datetime(m["sent"].astimezone(UTC))
        msg["From"] = f"{m['from_name']} <{m['from']}>"
        msg["To"] = m["to"] if "," in m["to"] else f"{ME[0]} <{m['to']}>"
        msg["Subject"] = m["subject"]
        msg["X-Demo-Synthetic"] = "true"
        msg.set_content(m["body"], cte="8bit")
        with open(os.path.join(folder, "emails", f"{m['email_id']}.eml"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(msg.as_string())
    index = [{"email_id": m["email_id"], "sent": _t(m["sent"]), "from": f"{m['from_name']} <{m['from']}>",
              "to": m["to"], "subject": m["subject"], "relevant": m["relevant"], "scenario": m["scenario"],
              "body": m["body"]} for m in mails]
    with open(os.path.join(folder, "emails.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    teams = build_teams(g)
    with open(os.path.join(folder, "teams_messages.json"), "w", encoding="utf-8") as fh:
        json.dump(teams, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(folder, "sop", "SOP-TT-014_handling_aggregation_mismatches.md"), "w",
              encoding="utf-8") as fh:
        fh.write(SOP_AGGREGATION)
    with open(os.path.join(folder, "sop", "SOP-TT-021_responding_to_authority_trace_requests.md"), "w",
              encoding="utf-8") as fh:
        fh.write(SOP_TRACE)
    g.facts["emails"] = mails
    g.facts["teams"] = teams
    return {"emails": len(mails), "teams": len(teams)}
