# Track & Trace ontology tutorial part 3: Explore the ontology

In this tutorial step, explore your ontology in different ways. View the ontology in multiple canvas views,
explore its entity instances, and follow a pack through the aggregation hierarchy in the ontology's graph.

> [!NOTE]
> If you created the ontology with [the shortcut notebook](tutorial-1-2-shortcut.md), the entity type keys and
> the mapping tables are already set, so **Prepare the graph** is only a check. If the notebook reported
> "Relationship bindings: direct", add the mapping tables as described in that section.

## Explore canvas views

The home configuration canvas of ontology contains three views: full ontology, neighborhood and inheritance. To
switch views, select **Full ontology**, **Neighborhood** or **Inheritance** in the upper-right corner of the
canvas.

- **Full ontology** shows all entity types and relationship types. Select **Pack** in the **Explorer** to center
  it, and follow the chain Pack → Bundle → Shipping Case → Pallet → Shipment → Warehouse → Market.
- **Neighborhood** shows the modeled relationships of one entity type. Select **Shipment**: it connects to Pallet,
  Factory, Warehouse, Partner and Authority Submission. This is the "hub" the storyline keeps coming back to.
- **Inheritance** shows the inheritance structure. Select **Warehouse** to see Hub and Distributor, or **Product**
  to see Cigarette and Heated Tobacco Stick.

## Explore entity instances

When you bound data to your entity types in part 1, ontology automatically created instances of those entity
types that map to the source data rows.

1. Start in the **Home** configuration canvas of ontology.
1. Select the **Shipment** entity type, and then select **Entity type > Open details** from the ribbon.
1. Open the **Instances** tab. You see the shipments from the lakehouse table, with properties like
   shipment_status, planned_departure and estimated_arrival. Find `{{s2_ship}}`: its status is **DELAYED**,
   it left at {{s2_actual_dep}} instead of {{s2_planned_dep}}, and its estimated arrival is {{s2_eta}}.
1. Open the instances of **Shipping Case**. Most cases have aggregation_status **COMPLETE**; the
   {{s1_cases}} **MISMATCH** cases are on line {{s1_line}}.

> [!TIP]
> If data bindings don't load, confirm that the source tables exist with matching column names, and that your
> Fabric identity has access to the data.

## Explore ontology graph

Ontology comes with an optional built-in instance of graph in Microsoft Fabric. It isn't required for the
ontology or the agents, but it shows the pack-to-warehouse trace visually, which works well in the demo
(scene 4).

### Prepare the graph

Prepare data for graph visualization by defining an entity type key for each entity type. An entity type key
shows which field uniquely identifies a row. Entity types must have an entity type key to be eligible for graph
projection.

1. Select an entity type in the canvas and select **Entity type > Open details**.
1. Select **Define entity type key**, select the key from the following table, and select **Save**.

Repeat for each entity type that you plan to project, except the types marked *skip*.

| Entity type | Entity type key |
|---|---|
| Warehouse, Hub, Distributor | warehouse_id |
| Factory | factory_id |
| Production Line | line_id |
| Production Order | order_id |
| Product, Cigarette, Heated Tobacco Stick | sku |
| Pack | pack_uid |
| Bundle | bundle_uid |
| Shipping Case | case_uid |
| Pallet | pallet_uid |
| Shipment | shipment_id |
| Partner | partner_id |
| Market | market_id |
| Tax Authority | authority_id |
| Authority Submission | submission_id |
| Maintenance Event | log_id |
| Inventory Position | snapshot_id |
| Demand Forecast | forecast_id |
| Consumer Scan | scan_id |
| Trace Event, Scanner Telemetry, Line Production Day | skip |

> [!NOTE]
> Only delta tables from lakehouses or mirrored databases are supported. Trace Event and Scanner Telemetry
> (eventhouse) and Line Production Day (semantic model) use unsupported source types. Relationships also need a
> supported data binding with a single backing table. If you didn't set mapping tables in part 1, open each
> relationship you want to project, turn on **Use mapping table**, and use the table listed in the last column
> of the part 1 relationship tables. For example, for **aggregatedIntoBundle**, select Pack's *pack_uid* and
> Bundle's *bundle_uid*, choose the mapping table **pack**, and match its **pack_uid** and **bundle_uid** columns.

### Set up the graph instance

1. From the home canvas ribbon, select **Home > Manage > Graph**.
1. On **Review validation**, wait for validation to finish. Review the **Status** column, and select
   **Ineligible** for an entry to learn why it can't be projected.
1. Select **Select entities**.
1. On **Choose what to project**, select the eligible entity types and expand them to select their relationships.
   Each entity type becomes a node type, and each relationship type becomes an edge type. For the queries below,
   include at least Production Line, Production Order, Pack, Bundle, Shipping Case, Pallet, Shipment, Warehouse,
   Distributor and Authority Submission, and the relationships between them.
1. Select **Continue**. On **Projection summary**, review your selected entities and relationships.
1. Select **Materialize**. Creating and loading the graph model might take several minutes. Wait for
   **Materialization status** to show **Graph materialized** and a **Complete** refresh status.

### Explore the graph

1. In your Fabric workspace, open the graph model associated with your ontology.
1. In the graph model, select **Query > Query now**. The graph queryset view opens.
1. On the right side of the queryset, select the puzzle piece icon to expand the **Components** pane. It lists
   the nodes and edges available in your graph.
1. Under **Nodes**, select Pack, Bundle, Shipping Case, Pallet, Shipment and Warehouse. Under **Edges**, select
   the edges between them (they're named after their origin and target entity types). The nodes and
   relationships are added to the canvas.
1. Select **Path query** from the top ribbon and confirm the **Switch** when prompted.

**Query 1: the trace of one pack (scenario S4).** Enter the following query details:

- **Start node**: Pack
- **End node**: Warehouse
- **Filter start node**: pack_uid = `{{s4_pack}}`
- **Max hops**: 5

Select **Run query** to render the result in the query result canvas and the path results pane. Look for the
direct path through the aggregation hierarchy:

Pack `{{s4_pack}}` → Bundle `{{s4_bundle}}` → Shipping Case `{{s4_case}}` → Pallet `{{s4_pallet}}` →
Shipment `{{s4_ship}}` → Warehouse `{{s4_wh}}` ({{s4_wh_name}}).

If production orders are part of the graph, the result can also show detours through the pack's production
order to other cases of the same order. The direct path above is the trace.

Keep this result open in a browser tab for scene 4 of the demo: it's the visual version of the authority's
trace request.

**Query 2: the impact of the aggregation mismatch (scenarios S1 and S3).** Add Production Line, Production Order
and Authority Submission with their edges to the canvas, and enter:

- **Start node**: Production Line
- **End node**: Authority Submission
- **Filter start node**: line_id = `{{s1_line}}`
- **Filter end node**: rejection_code = `MISSING_AGGREGATION_DATA`
- **Max hops**: 5

The paths run from the line through production order `{{s1_order}}`, its shipping cases and pallets, to the
shipments `{{s1_ship1}}` and `{{s1_ship2}}`, and end at the rejected submissions **{{s3_sub1}}** and
**{{s3_sub2}}**.

If you want, try more queries and graph features before you continue.

## Next steps

In this step, you explored the ontology in the canvas, through entity instances and as a graph. Next, use the
ontology agent to explore the data further with natural language: [Use the ontology agent](tutorial-4-use-agent.md).
