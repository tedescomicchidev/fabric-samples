"""The Track & Trace ontology of tutorial parts 1 and 2, as data.

notebooks/create_ontology.ipynb embeds this spec and turns it into an ontology (preview) definition, so
you can skip parts 1 and 2. validate_data.py checks that every name, key, mapping table, description,
synonym and rule here also appears in the tutorial pages, and that every column exists in the CSV files.
When you change the ontology in tutorial_templates/tutorial-1-*.md or tutorial-2-*.md, change it here too.

Sources: "lakehouse" entity types and relationship types are created by the notebook. "eventhouse" and
"semantic_model" ones aren't, because the ontology definition format for those bindings isn't documented
yet; the notebook prints the steps to add them in the ontology editor.
"""
from __future__ import annotations

ONTOLOGY_NAME = "TrackTraceOntology"
LAKEHOUSE_NAME = "TrackTraceLH"
EVENTHOUSE_NAME = "TrackTraceEH"
SEMANTIC_MODEL_NAME = "TrackTraceKPIs"


def _e(name, table, key=None, source="lakehouse", base=None, renames=None, description=None, synonyms=None,
       annotations=None, properties=None, note=None):
    return {"name": name, "table": table, "key": key, "source": source, "base": base,
            "renames": renames or {}, "description": description, "synonyms": synonyms or [],
            "annotations": annotations or [], "property_descriptions": properties or {}, "note": note}


ENTITY_TYPES = [
    _e("Warehouse", "warehouse", "warehouse_id", renames={"name": "warehouse_name"},
       properties={"demand_share_pct": "Share of the market's demand served by this warehouse, in percent."}),
    _e("Distributor", "warehouse", "warehouse_id", base="Warehouse",
       description="Filtered warehouse binding where warehouse_type = DISTRIBUTOR. A distributor receives "
                   "shipments from the factories and supplies retail in its market."),
    _e("Hub", "warehouse", "warehouse_id", base="Warehouse",
       description="Filtered warehouse binding where warehouse_type = HUB. A hub receives full trucks from the "
                   "factories and serves all or most of its market."),
    _e("Factory", "factory", "factory_id", renames={"name": "factory_name"}),
    _e("Production Line", "production_line", "line_id", renames={"status": "line_status"}),
    _e("Production Order", "production_order", "order_id", renames={"status": "order_status"}),
    _e("Product", "product", "sku",
       properties={"sku": "Enterprise product identifier (stock keeping unit)."}),
    _e("Cigarette", "product", "sku", base="Product",
       description="Filtered product binding where category = Cigarettes."),
    _e("Heated Tobacco Stick", "product", "sku", base="Product",
       description="Filtered product binding where category = Heated tobacco sticks."),
    _e("Pack", "pack", "pack_uid", renames={"status": "pack_status"},
       description="Smallest serialized saleable unit. Each pack carries a unique serial code (UID) that is "
                   "commissioned on the packaging line.",
       synonyms=["UID", "serial code", "serialized pack", "unit pack"],
       properties={"pack_status": "AGGREGATED (at the factory), DISPATCHED (in transit), ARRIVED (at the "
                                  "destination warehouse), DECOMMISSIONED (removed, for example a quality "
                                  "reject), AGGREGATION_INCOMPLETE (its bundle was never aggregated into a case)."},
       note="The largest table"),
    _e("Bundle", "bundle", "bundle_uid", renames={"status": "bundle_status"},
       description="Group of packs aggregated under one bundle UID. A full bundle holds packs_per_bundle packs of "
                   "its product.",
       synonyms=["carton"],
       properties={"bundle_status": "AGGREGATED = linked to a shipping case. NOT_AGGREGATED = no parent case: an "
                                    "aggregation gap."}),
    _e("Shipping Case", "shipping_case", "case_uid",
       description="Group of bundles aggregated under one case UID. A full case holds bundles_per_case bundles of "
                   "its product.",
       synonyms=["case", "master case", "outer case"],
       properties={
           "aggregation_status": "COMPLETE = all expected bundles aggregated. MISMATCH = fewer bundles aggregated "
                                 "than expected and not corrected. REWORKED = corrected by disaggregation and "
                                 "re-aggregation.",
           "bundle_count": "Bundles aggregated into the case. Compare with expected_bundle_count.",
           "expected_bundle_count": "Bundles in a full case: bundles_per_case of the product.",
       }),
    _e("Pallet", "pallet", "pallet_uid", renames={"status": "pallet_status"},
       description="Logistics unit built from shipping cases (cases_per_pallet of the product).",
       properties={"pallet_status": "OPEN (being built), READY (closed, waiting for dispatch), DISPATCHED, "
                                    "ARRIVED."}),
    _e("Shipment", "shipment", "shipment_id", renames={"status": "shipment_status"},
       description="One truck departure from a factory to a warehouse.",
       synonyms=["consignment", "load", "truck"],
       properties={
           "shipment_status": "PLANNED, IN_TRANSIT, DELAYED (estimated arrival more than 4 hours after the "
                              "planned arrival), DELIVERED.",
           "estimated_arrival": "Latest estimated arrival time. Equals actual_arrival once the shipment is "
                                "delivered.",
       }),
    _e("Market", "market", "market_id", renames={"name": "market_name"},
       description="Market of destination. regulation_profile defines which authority submissions are required.",
       synonyms=["market of destination", "intended market"],
       properties={"regulation_profile": "Required submissions. DISPATCH_AND_ARRIVAL and TAX_STAMP_RECONCILIATION: "
                                         "dispatch and arrival. FULL_HIERARCHY_AT_DISPATCH: dispatch, with the "
                                         "complete pack-to-pallet hierarchy. ARRIVAL_ONLY: arrival."}),
    _e("Tax Authority", "tax_authority", "authority_id", renames={"name": "authority_name"}),
    _e("Authority Submission", "authority_submission", "submission_id", renames={"status": "submission_status"},
       description="Notification to a market's tax authority about the dispatch or arrival of a shipment.",
       synonyms=["regulatory notification", "dispatch notification", "arrival notification"],
       properties={
           "submission_status": "ACCEPTED, REJECTED or PENDING. A rejection is resolved when a later submission "
                                "has resubmission_of equal to its submission_id.",
           "sla_due_ts": "Deadline for an accepted submission: event_ts plus the authority's submission_sla_hours.",
       }),
    _e("Partner", "partner", "partner_id", renames={"name": "partner_name"}),
    _e("Inventory Position", "inventory_snapshot", "snapshot_id",
       annotations=[
           ("Days of cover", "qty_on_hand divided by the daily demand of the warehouse. Daily demand is the average "
                             "forecast_qty of the next 7 days for the warehouse's market and product, times "
                             "demand_share_pct / 100. All quantities are shipping cases."),
           ("Low days of cover", "Days of cover less than 3"),
       ],
       properties={"qty_on_hand": "Shipping cases on hand at the snapshot time (uom = CASE), not packs."}),
    _e("Demand Forecast", "demand_forecast", "forecast_id"),
    _e("Maintenance Event", "maintenance_log", "log_id",
       description="Maintenance log entry for a production line. SCANNER_FAULT, OPERATING_MODE_CHANGE (for example "
                   "bypass mode) and REPAIR entries explain aggregation problems."),
    _e("Consumer Scan", "consumer_scan", "scan_id",
       properties={"result": "VALID; UNKNOWN (the UID doesn't exist); DUPLICATE (the UID was scanned far away "
                             "shortly before)."}),
    _e("Trace Event", "TraceEvent", source="eventhouse",
       description="Track & Trace event. COMMISSION activates a UID; AGGREGATE links child_count children to the "
                   "parent object_uid; DISAGGREGATE removes them; DISPATCH and ARRIVE move a pallet with a shipment; "
                   "DECOMMISSION deactivates a UID; SCAN_CONSUMER is a scan in the consumer app.",
       synonyms=["serialization event"]),
    _e("Scanner Telemetry", "LineScannerTelemetry", source="eventhouse",
       description="5-minute readings of the bundle and case aggregation scanners of each line: codes expected, "
                   "codes read, read rate, scanner status and station mode.",
       properties={
           "read_rate_pct": "Percentage of expected codes read in the 5-minute interval.",
           "station_mode": "NORMAL, or BYPASS: the line keeps running when codes aren't read, so aggregation can be "
                           "incomplete.",
       }),
    _e("Line Production Day", "ProductionDaily", source="semantic_model"),
]


def _r(name, origin, origin_prop, target, target_prop, mapping, optional=False, description=None):
    """mapping: (table, origin key column, target key column) for a lakehouse mapping table, or the text of
    the tutorial's mapping column for relationships that the notebook doesn't create."""
    rel = {"name": name, "origin": origin, "origin_property": origin_prop, "target": target,
           "target_property": target_prop, "optional": optional, "description": description}
    if isinstance(mapping, tuple):
        rel.update(source="lakehouse", mapping_table=mapping[0], mapping_columns=[mapping[1], mapping[2]],
                   mapping_text=None)
    else:
        rel.update(source="eventhouse" if "Event" in target or "Telemetry" in target else "semantic_model",
                   mapping_table=None, mapping_columns=None, mapping_text=mapping)
    return rel


RELATIONSHIP_TYPES = [
    _r("hasLine", "Factory", "factory_id", "Production Line", "factory_id",
       ("production_line", "factory_id", "line_id")),
    _r("runsOrder", "Production Line", "line_id", "Production Order", "line_id",
       ("production_order", "line_id", "order_id")),
    _r("producesProduct", "Production Order", "sku", "Product", "sku", ("production_order", "order_id", "sku")),
    _r("aggregatedIntoBundle", "Pack", "bundle_uid", "Bundle", "bundle_uid", ("pack", "pack_uid", "bundle_uid"),
       description="The pack was aggregated into this bundle."),
    _r("aggregatedIntoCase", "Bundle", "case_uid", "Shipping Case", "case_uid", ("bundle", "bundle_uid", "case_uid"),
       description="The bundle was aggregated into this shipping case. A bundle without a case wasn't aggregated."),
    _r("aggregatedIntoPallet", "Shipping Case", "pallet_uid", "Pallet", "pallet_uid",
       ("shipping_case", "case_uid", "pallet_uid"),
       description="The shipping case was aggregated onto this pallet."),
    _r("caseProducedUnder", "Shipping Case", "order_id", "Production Order", "order_id",
       ("shipping_case", "case_uid", "order_id"),
       description="The production order, and so the line and time, under which the case was packed."),
    # After caseProducedUnder: with direct bindings (the notebook's fallback) the second path from a pack to its
    # production order becomes the inactive one, and caseProducedUnder (scene 1) stays active.
    _r("commissionedUnder", "Pack", "order_id", "Production Order", "order_id", ("pack", "pack_uid", "order_id")),
    _r("loadedOn", "Pallet", "shipment_id", "Shipment", "shipment_id", ("pallet", "pallet_uid", "shipment_id"),
       description="The pallet travels with this shipment."),
    _r("originatesAt", "Shipment", "from_location", "Factory", "factory_id",
       ("shipment", "shipment_id", "from_location"),
       description="Identifies the factory sending the shipment."),
    _r("deliversTo", "Shipment", "to_location", "Warehouse", "warehouse_id", ("shipment", "shipment_id", "to_location"),
       description="Identifies the warehouse receiving the shipment."),
    _r("carriedBy", "Shipment", "partner_id", "Partner", "partner_id", ("shipment", "shipment_id", "partner_id"),
       description="Identifies the carrier of the shipment."),
    _r("locatedIn", "Warehouse", "market_id", "Market", "market_id", ("warehouse", "warehouse_id", "market_id")),
    _r("reportsShipment", "Authority Submission", "shipment_id", "Shipment", "shipment_id",
       ("authority_submission", "submission_id", "shipment_id"),
       description="The submission notifies the tax authority about this shipment's dispatch or arrival."),
    _r("submittedTo", "Authority Submission", "authority_id", "Tax Authority", "authority_id",
       ("authority_submission", "submission_id", "authority_id")),
    _r("stockedAt", "Inventory Position", "warehouse_id", "Warehouse", "warehouse_id",
       ("inventory_snapshot", "snapshot_id", "warehouse_id"),
       description="The warehouse holding the stock."),
    _r("stockOfProduct", "Inventory Position", "sku", "Product", "sku", ("inventory_snapshot", "snapshot_id", "sku")),
    _r("forecastForMarket", "Demand Forecast", "market_id", "Market", "market_id",
       ("demand_forecast", "forecast_id", "market_id")),
    _r("forecastForProduct", "Demand Forecast", "sku", "Product", "sku", ("demand_forecast", "forecast_id", "sku")),
    _r("loggedOn", "Maintenance Event", "line_id", "Production Line", "line_id", ("maintenance_log", "log_id", "line_id"),
       description="Identifies the line the maintenance entry is about."),
    _r("hasScannerReading", "Production Line", "line_id", "Scanner Telemetry", "line_id",
       "none (eventhouse, not projected)", description="Aggregation scanner readings of the line."),
    _r("hasTraceEvent", "Pack", "pack_uid", "Trace Event", "object_uid", "none (eventhouse, not projected)"),
    _r("measuredOn", "Line Production Day", "line_id", "Production Line", "line_id",
       "none (semantic model, not projected)"),
    # Extra context (optional)
    _r("targetsMarket", "Production Order", "target_market_id", "Market", "market_id",
       ("production_order", "order_id", "target_market_id"), optional=True),
    _r("packOfProduct", "Pack", "sku", "Product", "sku", ("pack", "pack_uid", "sku"), optional=True),
    _r("regulates", "Tax Authority", "market_id", "Market", "market_id", ("tax_authority", "authority_id", "market_id"),
       optional=True),
    _r("scanOfPack", "Consumer Scan", "pack_uid", "Pack", "pack_uid", ("consumer_scan", "scan_id", "pack_uid"),
       optional=True),
    _r("hasBundleEvent", "Bundle", "bundle_uid", "Trace Event", "object_uid", "none", optional=True),
    _r("hasCaseEvent", "Shipping Case", "case_uid", "Trace Event", "object_uid", "none", optional=True),
    _r("hasPalletEvent", "Pallet", "pallet_uid", "Trace Event", "object_uid", "none", optional=True),
]

RULES = [
    {"name": "Aggregation mismatch",
     "statement": "A shipping case has an aggregation mismatch when its bundle_count is lower than the "
                  "bundles_per_case of its product. Authorities that require the full hierarchy reject submissions "
                  "for shipments that contain such cases.",
     "entities": ["Shipping Case", "Product"]},
    {"name": "Scanner degradation",
     "statement": "An aggregation scanner is degraded when its read rate stays below 98% for more than 15 minutes, "
                  "or when its station runs in BYPASS mode.",
     "entities": ["Production Line", "Scanner Telemetry"]},
    {"name": "Delayed shipment",
     "statement": "A shipment is delayed when it departed more than 4 hours after its planned departure, or when "
                  "its estimated arrival is more than 4 hours after its planned arrival.",
     "entities": ["Shipment"]},
    {"name": "Submission SLA breach",
     "statement": "An authority submission breaches its SLA when it isn't accepted by sla_due_ts, which is the "
                  "event time plus the authority's submission_sla_hours.",
     "entities": ["Authority Submission", "Tax Authority"]},
    {"name": "Supply risk",
     "statement": "A warehouse has a supply risk for a product when its days of cover is below 3. A warehouse in "
                  "the same market with more than 7 days of cover can transfer the stock above 7 days of cover.",
     "entities": ["Inventory Position", "Demand Forecast", "Warehouse"]},
    {"name": "Suspicious consumer scan",
     "statement": "A pack is suspicious when it's scanned in two different countries within 24 hours, or when a "
                  "scanned UID doesn't exist.",
     "entities": ["Consumer Scan", "Pack"]},
]


def notebook_spec():
    """The part of the spec that the notebook embeds (JSON-serializable)."""
    return {"ontology": ONTOLOGY_NAME, "lakehouse": LAKEHOUSE_NAME, "eventhouse": EVENTHOUSE_NAME,
            "semantic_model": SEMANTIC_MODEL_NAME, "entity_types": ENTITY_TYPES,
            "relationship_types": RELATIONSHIP_TYPES, "rules": RULES}
