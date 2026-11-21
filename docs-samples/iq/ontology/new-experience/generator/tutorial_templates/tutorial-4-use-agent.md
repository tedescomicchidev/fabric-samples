# Track & Trace ontology tutorial part 4: Use the ontology agent

In this tutorial step, use the ontology agent to ask questions in natural language and get answers grounded in
the ontology's definitions and bindings. It's also the first check that the ontology answers the demo questions
correctly, before you build the demo agents in part 5.

## Get started with ontology agent

The ontology agent (preview) is an AI-powered Copilot that helps you build and operate ontologies over the data
in your Fabric workspace, through a chat interface and natural language. To open it, select **Ontology agent**
from the top ribbon in the home canvas. The agent opens in a pane on the right side of the screen, in **Plan**
mode by default. In Plan mode, the agent can query and explore the ontology, but it doesn't make any changes.

> [!IMPORTANT]
> Write dates explicitly. The data is dated around {{today}}, and words like "yesterday" are resolved
> against the real current date.

## Ask questions in natural language

Enter the following question in the ontology agent text box and send it:

> Which shipping cases produced on line PL-02-L3 on {{yday}} have an aggregation mismatch?

The agent reasons for a short time and then answers from your ontology. Expect {{s1_cases}} shipping cases,
created between {{s1_first}} and {{s1_last}} UTC, all from production order `{{s1_order}}` ({{s1_product}} for
Market Gamma). {{s1_miss1}} cases miss one bundle and {{s1_miss2}} miss two.

Explore the ontology further with the following questions, one per demo scene. The expected answers come from
the generated data.

| Scene | Question | Expected answer |
|---|---|---|
| 1 | How many packs were commissioned per factory on {{yday}}, how many shipping cases had an aggregation mismatch, and which authority submissions were rejected? | {{packs_total}} packs in total (see the table below). {{s1_cases}} mismatched cases, all on {{s1_line}}. {{s3_subs}} were rejected by {{s3_auth}}. |
| 2 | Why did production line PL-02-L3 have an aggregation mismatch on {{yday}}? What do the maintenance log and the scanner telemetry show? | Scanner fault (camera 2) logged at {{s1_fault}}, case aggregation station switched to bypass at {{s1_bypass}}, repaired at {{s1_repair}} UTC. The first mismatched case followed the fault by {{s1_fault_gap}} minutes. The case scanner's read rate was {{s1_read_avg}} on average while in bypass. |
| 2 | What was the aggregation error rate per production line on {{yday}}? | {{s1_line}}: {{s1_line_rate}} ({{s1_cases}} of {{s1_line_cases}} cases). All other lines: 0%. This uses the *Aggregation Error Rate %* metric from the semantic model. |
| 3 | Which shipments to Market Beta are delayed, and how many pallets, shipping cases and packs do they carry? | `{{s2_ship}}` to {{s2_wh}}, {{s2_delay}} hours late, estimated arrival {{s2_eta}}: {{s2_pallets}} pallets, {{s2_cases}} cases, {{s2_packs}} packs. |
| 4 | Provide the full trace of pack {{s4_pack}}, including the carrier and the authority submissions. | Commissioned {{s4_commissioned}} on {{s4_line}} under `{{s4_order}}` → bundle `{{s4_bundle}}` → case `{{s4_case}}` → pallet `{{s4_pallet}}` → shipment `{{s4_ship}}` ({{s4_carrier}}, dispatched {{s4_dispatched}}, arrived {{s4_arrived}}) → {{s4_wh}} {{s4_wh_name}}. Submissions {{s4_subs}}. |
| 5 | Which warehouses in Market Beta have less than 3 days of cover for {{s5_sku}}, and which warehouse in the same market could transfer stock? | {{s5_d1}}: {{s5_d1_qty}} cases, {{s5_d1_daily}} cases a day, {{s5_d1_cover}} days; {{s5_d1_transit}} cases are in transit on the delayed truck. {{s5_d2}}: {{s5_d2_qty}} cases, {{s5_d2_cover}} days; about {{s5_release}} cases can move while it keeps 7 days. |
| 6 | Which packs were scanned by consumers in two different countries within 24 hours? | `{{s6_pack}}`: {{s6_where1}} at {{s6_t1}}, then {{s6_where2}} at {{s6_t2}}, {{s6_km}} km away. |

Production on {{yday}}, for the scene 1 question:

{{kpi_table}}

## Answer the scenario question

Use the agent to answer the major question of the Track & Trace scenario:

> Which shipments dispatched on {{yday}} contain shipping cases with an aggregation mismatch, which
> authority submissions were rejected because of them, and what do the maintenance log and the scanner
> telemetry of the producing line show for the same time?

The agent considers your ontology and queries your data sources. Expect:

- `{{s1_ship1}}`, dispatched {{s1_ship1_dep}}, now {{s1_ship1_status}}: {{s1_ship1_n}} of its {{s1_ship1_cases}} cases have
  a mismatch. Submission **{{s3_sub1}}** was rejected with `MISSING_AGGREGATION_DATA`.
- `{{s1_ship2}}`, dispatched {{s1_ship2_dep}}, now {{s1_ship2_status}}: {{s1_ship2_n}} of {{s1_ship2_cases}} cases.
  Submission **{{s3_sub2}}** was rejected for the same reason.
- Both rejections are past Market Gamma's {{s3_sla}}-hour SLA.
- Maintenance log of {{s1_line}}: `SCANNER_FAULT` at {{s1_fault}}, `OPERATING_MODE_CHANGE` to bypass at
  {{s1_bypass}}, `REPAIR` at {{s1_repair}} UTC.
- Scanner telemetry: the case aggregation station was `DEGRADED` and in `BYPASS` from {{s1_bypass}} to {{s1_repair}},
  with read rates down to {{s1_read_min}}, below the 98% in the *Scanner degradation* rule.

If an answer is incomplete, check the relationship bindings from part 1 and the rules from part 2, then ask again.
Rephrasing with the business terms from the metadata (for example "aggregation mismatch" or "bypass mode") also
helps.

## Next steps

In this step, you used natural language to answer the scenario's questions with the ontology agent. Next, build
the agents that bring these answers into Copilot: [Build the demo agents](tutorial-5-build-demo-agents.md).
