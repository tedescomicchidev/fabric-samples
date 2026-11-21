# Track & Trace ontology tutorial part 6: Run the demo

This part is the demo script: "A day in the life of a Track & Trace expert, 12 months from now". It has seven
scenes in about 30 minutes, and each scene is one prompt in Copilot. For every scene you get the prompt, the
expected answer from the data, the point it makes for the audience, and a fallback.

Show finished results; don't build anything live. Parts 0 to 5 are the preparation.

## Before you start

- **Dates.** The prompts below use explicit dates, so they work on any day. The T&T Copilot instructions also fix
  "today" to {{today}}. If you want to say "yesterday" in a rehearsal on another day, regenerate the data with
  `--as-of` set to that week's Wednesday, 07:00 UTC, and reload it.
- **Warm up.** About ten minutes before the session, ask each data agent one question. The first answer after a
  pause takes longer.
- **Browser tabs, in this order:** Microsoft 365 Copilot with T&T Copilot; the graph path from
  [part 3](tutorial-3-explore-ontology.md#explore-the-graph) (query 1); the ontology canvas; the mock incident
  list; the demo user's Outlook.
- **Backup.** Take a screenshot of every expected answer during the last rehearsal. If the network or a preview
  feature fails, show the screenshot and keep going.
- **Reset.** After each rehearsal, delete the incidents, tasks and drafts the demo created, and start a new chat.

## Timing

| Segment | Minutes | Takeaways |
|---|---:|---|
| Opening | 2 | |
| Scene 1: Morning briefing | 4 | 3, 4 |
| Scene 2: Anomaly drill-down | 5 | 1, 2 |
| Scene 3: Relevant email surfaced | 3 | 4 |
| Scene 4: Authority request | 4 | 1, 5 |
| Scene 5: Close the loop with supply chain | 5 | 4, 5 |
| Scene 6: Action | 4 | 3, 5 |
| Closing | 3 | all |
| Scene 7: Governance teaser (optional) | +2 | 3 |

The takeaways are the five success criteria from [part 0](tutorial-0-introduction.md#what-the-audience-should-leave-with):
(1) how Fabric data agents work over Track & Trace data, (2) why semantic business context matters, (3) Copilot
as the UI for composable agents, (4) Track & Trace connected with supply chain and work context, and (5) AI that
supports decisions, not just answers.

## Opening (2 minutes)

- Introduce Marta K.: Track & Trace Operations Specialist, three factories, four markets. Her mornings today:
  reconciling systems by hand, chasing emails, finding aggregation errors late.
- "We'll spend one morning with her, 12 months from now. Everything you'll see is real Fabric and Copilot
  technology, over synthetic data. The serialization platform, the incident tool and the authorities are mocked."
- "Watch for one thing: an email, a delayed truck, a regulatory rejection and a stock risk get connected without
  anyone doing the joining by hand."

## Scene 1: 08:00 Morning briefing (4 minutes)

**Prompt** (T&T Copilot):

> Good morning. Give me my Track & Trace briefing for {{today}}: production and aggregation errors per factory
> for {{yday}}, rejected or overdue authority submissions, delayed shipments, and only the emails and Teams
> messages since {{yday}} that affect today's decisions.

**Expected answer:**

- Production on {{yday}}: {{packs_total}} packs commissioned.

{{kpi_table}}

- {{s1_cases}} shipping cases with an aggregation mismatch, all on {{s1_line}} ({{s1_line_rate}} of that line's
  cases).
- {{s3_subs}} rejected by Market Gamma for missing aggregation data, both past the {{s3_sla}}-hour SLA.
- `{{s2_ship}}` to {{s2_wh_name}} is {{s2_delay}} hours late, with an estimated arrival of {{s2_eta}}.
- The {{email_relevant}} relevant emails out of {{email_count}}: the PL-02 shift lead on the scanner bypass,
  Gamma's two rejections, Compliance asking about them, Northgate Haulage's delay notice, the 3PL's stock note
  for Market Beta, and Beta's trace request. The {{email_noise}} others (menus, newsletters, training reminders)
  aren't mentioned.

**What it demonstrates:** Copilot as the single UI over several agents (3), and Work IQ deciding which emails are
relevant to a Track & Trace decision (4).

**Say:** "There are {{email_count}} emails in this inbox. Copilot didn't summarize all of them. It picked the
{{email_relevant}} that touch a Track & Trace decision and put them next to the numbers."

**Fallback:** ask the data part and the email part as two prompts.

## Scene 2: 08:15 Anomaly drill-down (5 minutes)

**Prompt:**

> Why did Factory PL-02 Line 3 have an aggregation mismatch on {{yday}}? How many shipping cases are affected,
> and where are they now?

**Expected answer:**

- **Root cause:** the case aggregation scanner (camera 2) on {{s1_line}}. Fault logged at {{s1_fault}} UTC, station
  switched to bypass mode at {{s1_bypass}}, repaired at {{s1_repair}}. The first mismatched case was packed at
  {{s1_first}}, {{s1_fault_gap}} minutes after the fault, and the last at {{s1_last}}.
- **Telemetry:** while in bypass, the case scanner read {{s1_read_avg}} of the codes on average, and as little as
  {{s1_read_min}}, against the 98% of the *Scanner degradation* rule.
- **Impact:** {{s1_cases}} cases of order `{{s1_order}}` ({{s1_product}} for Market Gamma). {{s1_miss1}} miss one
  bundle and {{s1_miss2}} miss two. {{s1_bundles}} bundles, with {{s1_packs}} packs, aren't linked to any case.
- **Where they are:** {{s1_ships}}.
- **Next steps** from SOP-TT-014: re-scan and re-aggregate the cases, send corrected submissions, and open a P1
  incident because the SLA is already breached.

**What it demonstrates:** a Fabric data agent answering over lakehouse, eventhouse and semantic model data at
once (1), and the ontology supplying the meaning (2): no one told the agent that a bypass explains a mismatch.
The relationships (line → maintenance log → telemetry → cases → shipments) and the rules from part 2 did.

**Say:** "Today, a question like this means exports and manual reconciliation across systems. Here the business
vocabulary lives in the ontology, once, and every agent uses it."

**Fallback:** the same question in the ontology agent ([part 4](tutorial-4-use-agent.md)), or graph query 2 from
part 3.

## Scene 3: 09:00 Relevant email surfaced (3 minutes)

**Prompt:**

> Summarize the delay notice from Northgate Haulage and tell me exactly what's on that truck: pallets, shipping
> cases, packs and products.

**Expected answer:**

- From the email: `{{s2_ship}}`, PL-01 to {{s2_wh_name}}. Planned departure {{s2_planned_dep}}, actual
  {{s2_actual_dep}} ({{s2_delay}} hours late, tractor unit breakdown). Revised ETA {{s2_eta}} instead of
  {{s2_planned_arr}}.
- From the T&T Data Agent: {{s2_pallets}} pallets, {{s2_cases}} shipping cases and {{s2_packs}} packs.
  {{s2_sku_split}}.

**What it demonstrates:** an unstructured email linked to the aggregation tree (4). The carrier's email has one
shipment ID; the ontology turns it into pallets, cases, packs and products.

**Say:** "Notice which product dominates the truck: {{s5_brand}}. Keep that in mind for 11:00."

## Scene 4: 10:00 Authority request (4 minutes)

**Prompt:**

> The Beta Revenue and Stamp Office asked for the full trace of pack {{s4_pack}}. Give me the trace and draft
> the reply following SOP-TT-021.

**Expected answer:**

- {{s4_product}}, commissioned {{s4_commissioned}} at {{s4_factory}}, line {{s4_line}}, order `{{s4_order}}`.
- Bundle `{{s4_bundle}}` → shipping case `{{s4_case}}` → pallet `{{s4_pallet}}`.
- Shipment `{{s4_ship}}` with {{s4_carrier}}: dispatched {{s4_dispatched}}, received by {{s4_wh}}
  {{s4_wh_name}} at {{s4_arrived}}.
- Authority submissions {{s4_subs}}.
- SOP check: no aggregation mismatch, no disaggregation and no duplicate consumer scan on this chain.
- A reply quoting reference **{{s4_ref}}**, as an Outlook draft or as text. It isn't sent.

Then switch to the graph tab and show the same path visually.

**What it demonstrates:** a full trace in seconds instead of hours (1), and a draft that follows the SOP and waits
for a person to review it (5).

## Scene 5: 11:00 Close the loop with supply chain (5 minutes)

**Prompt:**

> Given the Northgate delay, is Market Beta at risk of running out of stock this week? If so, what should we do?

**Expected answer:**

- {{s5_d1}} {{s5_d1_name}}, {{s5_sku}} {{s5_brand}}: {{s5_d1_qty}} cases on hand and {{s5_d1_daily}} cases of demand a
  day, so **{{s5_d1_cover}} days of cover**, below the 3-day threshold. Its {{s5_d1_transit}} cases in transit are on
  the delayed truck `{{s2_ship}}` (ETA {{s2_eta}}). Without that truck, it runs out around {{s5_runout}}.
- {{s5_d2}} {{s5_d2_name}}: {{s5_d2_qty}} cases, {{s5_d2_cover}} days of cover, about {{s5_release}} cases above 7 days.
- **Recommendation:** move {{s5_pallets}} pallets ({{s5_move}} cases) of {{s5_sku}} from {{s5_d2}} to {{s5_d1}}. That
  brings {{s5_d1}} to {{s5_d1_after}} days and leaves {{s5_d2}} with {{s5_d2_after}}. The 3PL's email offers a free
  shuttle slot this Wednesday afternoon, for up to 6 pallets.

**What it demonstrates:** Track & Trace closing the loop with supply chain (4), and a decision rather than an
answer (5). Two agents and one email contributed, and Copilot combined them.

**Say:** "This is the moment Track & Trace stops being only a compliance system. The same data that proves where
a pack went tells us where stock will run out, and what to do about it."

## Scene 6: 14:00 Action (4 minutes)

**Prompt:**

> Open a P1 incident for the PL-02 Line 3 aggregation mismatch with the affected shipments and rejected
> submissions, create a task for me to get the {{s1_cases}} cases re-scanned and the corrected Gamma submissions
> sent, and draft an email to Meridian 3PL to book the {{s5_pallets}}-pallet transfer from {{s5_d2}} to {{s5_d1}} on
> this afternoon's shuttle.

**Expected behavior:**

1. The agent shows the incident: priority P1 (the SLA is breached, as SOP-TT-014 requires), category Aggregation,
   line {{s1_line}}, related IDs `{{s1_order}}`, `{{s1_ship1}}`, `{{s1_ship2}}`, {{s3_subs}}. It asks you to confirm.
1. You confirm. The incident appears in the *T&T Incidents (mock ITSM)* list, and the task in Planner.
1. A draft to Meridian 3PL Services is in the demo user's **Drafts** folder. It isn't sent.

Show the list and the draft.

**What it demonstrates:** AI moving from insight to action (5), with a person approving every step, through tools
that could just as well be the real IT service management system (3).

**Say:** "The agent proposes, Marta decides. Nothing leaves the building without her."

## Closing (3 minutes)

- Recap the five takeaways with the scene that showed each one (see the timing table).
- **What's next, in 6 to 12 months:** an operations agent watching the ontology rules would have alerted Marta at
  {{s1_first}} on {{yday}}, when the first bad case was packed, not the next morning. The data agents can live
  where the data lives, for example in the serialization vendor's Fabric tenant, and plug into the same Copilot.
- Ask the audience about the open points in [part 7](tutorial-7-conclusion.md#open-points-to-validate): which
  exceptions are most common, and which supply chain signals matter most.

## Scene 7: 16:00 Governance teaser (optional, 2 minutes)

This scene is mocked. Show a prepared slide, or, if you have access, the agents page of the Microsoft 365 admin
center, with:

- The three agents (T&T Copilot, T&T Data Agent, Supply Chain Agent), their owners, and the data each one uses
  (ontology, lakehouse, mailbox).
- The identity: every query ran as Marta. A Fabric data agent in Microsoft 365 Copilot only returns data the user
  can access, with row-level and column-level security applied.
- The mock incident list's **Created by** column, which shows who approved each action.

**Prompt idea:** *Which agents acted today, on which data, under which identity?*

## Optional scene: consumer scan anomaly (S6)

Show it only if it suits the audience (it's an open point in part 7).

> Which packs were scanned by consumers in two different countries within 24 hours, and which scanned codes don't
> exist?

Expected: `{{s6_pack}}`, scanned in {{s6_where1}} at {{s6_t1}} and in {{s6_where2}}, {{s6_km}} km away, at {{s6_t2}}
({{s6_hours}} hours later). {{s6_unknown}} scans with codes that don't exist.

## If something goes wrong

- **An agent is slow or fails:** show the backup screenshot, or ask the same question in the ontology agent.
- **Copilot doesn't find an email:** name the sender or the subject in the prompt.
- **A date is interpreted wrongly:** put the explicit date in the prompt.
- **A number differs from this page:** compare with [`README_data.md`](../README_data.md). If they match each
  other but not the answer, ask the agent which IDs and time window it used.

## Next steps

Continue to [Conclude and clean up](tutorial-7-conclusion.md).
