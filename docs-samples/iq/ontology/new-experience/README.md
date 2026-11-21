# Ontology tutorial sample data: Track & Trace edition

This folder holds a **synthetic Track & Trace data set** for the
[Fabric IQ ontology (preview) tutorial](https://learn.microsoft.com/fabric/iq/ontology/tutorial-0-introduction),
replacing the Lakeshore Retail sample. It supports a demo storyline: a Track & Trace operations
specialist uses agents over an ontology to connect aggregation errors, authority submissions,
shipments and supply-chain risk.

All data is fictional. No real company, factory, market, customer or tax-authority data is used.

| Folder or file | Use in the tutorial |
|---|---|
| `lakehouse/` | Upload to the lakehouse **TrackTraceLH** and load each file (and the `pack` folder) to a table |
| `eventhouse/` | Load into the eventhouse **TrackTraceEH** as tables `TraceEvent` and `LineScannerTelemetry` |
| `notebooks/create_semantic_model.ipynb` | Run in Fabric to create the semantic model **TrackTraceKPIs** (replaces `SalesReport.pbix`) |
| `semantic-model/` | Source data of that semantic model, for reference. Don't upload it. |
| `work-context/` | Emails, Teams messages and SOPs for the Work IQ part of the demo |
| [`TUTORIAL_GUIDE.md`](TUTORIAL_GUIDE.md) | Step-by-step mapping of the tutorial to this data set |
| [`README_data.md`](README_data.md) | Row counts, seeded scenarios S1-S6 and design choices |
| `generator/` | `generate_data.py` (fixed seed) and `validate_data.py` |

Data snapshot: **2026-11-25 07:00 UTC**. To move the storyline to another week, run
`python generator/generate_data.py --as-of <a Wednesday>T07:00:00Z`.
