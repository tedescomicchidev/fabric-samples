# Track & Trace ontology tutorial shortcut: Create parts 1 and 2 with a notebook

Use this page instead of [part 1](tutorial-1-create-ontology.md) and [part 2](tutorial-2-enrich-ontology.md)
when you're short on time, for example to rebuild the demo environment before a rehearsal. A notebook creates
the ontology with the entity types, data bindings, relationship types, metadata and rules of parts 1 and 2. You
then add the three entity types that the notebook can't create, and continue with
[part 3](tutorial-3-explore-ontology.md).

The notebook works like the one that creates the semantic model in part 0: it calls the Fabric REST API. Here
it sends an ontology definition in the new-experience format, which is TMDL (the tabular model format) plus
ontology elements such as entity types, relationship types and rules. See
[Ontology (new) item definition](https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/ontology-definition).

> [!NOTE]
> If you present the demo with the "how it's built" angle, parts 1 and 2 are worth doing once by hand: building
> and describing the entity types is what makes the ontology understandable. The shortcut gives you the same
> result for rebuilds.

## What the notebook creates

| Ontology element | Created by the notebook | Left for you |
|---|---|---|
| Entity types bound to the **TrackTraceLH** tables | {{onto_base_count}}, with the property names from part 1 (for example *factory_name* and *pack_status*) | |
| Inherited entity types {{onto_inherited_list}} | Yes, if your tenant accepts entity type inheritance through the API | If the notebook skips them: optional, as in part 1 |
| Entity type keys | Yes, the keys from part 3 | |
| Descriptions, synonyms and additional metadata from part 2 | Yes | The metadata of the three entity types below |
| Relationship types | {{onto_rel_count}} ({{onto_rel_required}} needed for the storyline, {{onto_rel_optional}} for extra context), with the mapping tables from part 1 and the descriptions from part 2 | {{onto_later_rels}}, and the optional trace event relationship types |
| Business rules | All {{onto_rule_count}}, linked to the entity types that exist | Link *Scanner degradation* to Scanner Telemetry |
| {{onto_later_entities}} | No | Yes, about 10 minutes in the editor |

Why three entity types are left: the definition format documents bindings to lakehouse tables (Direct Lake)
only. Bindings to eventhouse tables and to semantic models, and the metrics that come from DAX measures, have no
documented definition format yet (November 2026), so the notebook doesn't guess one.

## Prerequisites

- Part 0 is complete: the lakehouse **TrackTraceLH** with its 18 tables under **dbo**, the eventhouse
  **TrackTraceEH** with **TraceEvent** and **LineScannerTelemetry**, and the semantic model **TrackTraceKPIs**.
  If you haven't done part 0 yet, use [the setup notebook](tutorial-0-2-shortcut.md) instead: it does part 0 and
  this page in one run.
- The workspace doesn't have an ontology called **{{onto_name}}** yet, or only an empty one.
- You're a contributor (or higher) in the workspace.

## Run the notebook

1. In your Fabric workspace, select **Import > Notebook > From this computer**, and choose
   `notebooks/create_ontology.ipynb`.
1. Open the notebook and select **Run all**. It runs on the Python or the PySpark kernel, and you don't need to
   attach a lakehouse.
1. Wait for the last cell. The run takes a few minutes, mostly waiting for the service.

The notebook does the following, one cell per step:

1. **Settings**. The defaults match the tutorial. You only change them in special cases (see below).
1. **Spec**. The ontology of parts 1 and 2 as data: entity types, source tables, property names, keys,
   descriptions, synonyms, relationship types with their mapping tables, and rules. The texts are the ones in the
   tutorial.
1. **Read the lakehouse**. Finds **TrackTraceLH** and its SQL analytics endpoint, and reads the column types of
   the Delta tables. That way the bindings match the tables exactly as **Load to Tables** created them.
1. **Build the definition**. Writes one TMDL part per table, entity type and rule, plus the relationships.
1. **Create and send**. Creates the ontology item and sends the definition. If the service doesn't accept
   relationship types with mapping tables, the notebook sends them as direct bindings instead. Then it adds the
   inherited entity types in a separate step, so a rejection there doesn't affect the rest.
1. **Check**. Reads the definition back, prints what the ontology contains, and lists the steps that are left.

When everything is accepted, the last cell starts with:

```text
{{onto_name}} has {{onto_entity_count}} entity types, {{onto_rel_count}} relationship types and {{onto_rule_count}} rules. Relationship bindings: mapping table.
```

If the inherited entity types were skipped, it shows {{onto_base_count}} entity types. Below it, the notebook
prints a numbered list of the remaining steps, with the texts to paste. The next section has the same steps.

### Settings

| Setting | Default | Change it when |
|---|---|---|
| `ONTOLOGY_NAME`, `LAKEHOUSE_NAME` | {{onto_name}}, TrackTraceLH | You used other names in part 0. The rest of the tutorial uses the defaults. |
| `INCLUDE_OPTIONAL_RELATIONSHIPS` | `True` | You want only the relationship types that the storyline needs. |
| `INCLUDE_INHERITED_TYPES` | `True` | You don't want Hub, Distributor, Cigarette and Heated Tobacco Stick. |
| `RELATIONSHIP_BINDING` | `"auto"` | `"mapping_table"` or `"direct"` to force one kind of relationship binding. |
| `REPLACE_EXISTING` | `False` | You want to rebuild an ontology that already has entity types. Its whole definition is replaced, including changes you made in the editor. |
| `SHOW_TMDL` | `False` | You want to see the definition parts before they're sent. |

### If the service rejects the definition

The notebook prints the service's error message for each attempt.

- **The definition isn't accepted with either kind of relationship binding.** The error names the part and the
  problem, for example a column type that the service doesn't accept, or a preview change in the definition
  format. (Missing tables are reported earlier, before anything is sent.) Set `SHOW_TMDL = True` to see the parts. If you can't fix it quickly, delete the empty ontology and
  follow parts 1 and 2 in the editor.
- **"Relationship bindings: direct".** The relationship types bind a foreign key column directly to the key of the
  other entity type, instead of using a mapping table. Some of them are inactive in the underlying model, because
  two active paths between the same tables aren't allowed. For the graph in part 3, turn on **Use mapping table**
  for the relationship types you project, with the tables from part 1. Part 3 describes how.
- **"The inherited entity types weren't accepted".** Entity type inheritance is rolling out gradually and isn't
  available in every tenant through the API. Add the four types in the editor if you want them for the
  **Inheritance** view in part 3; the storyline doesn't need them.

## Finish the ontology in the editor

Open **{{onto_name}}** in your workspace. The canvas shows the entity types and relationship types that the
notebook created. Add the rest as in part 1.

### Add Trace Event and Scanner Telemetry

1. On the **Home** tab of the ribbon, select **+ Add > Entity type**, enter *Trace Event*, and select **Add**.
1. Select **...** next to the entity type, then **Bind data**. Select the plus (**+**) button next to
   **Data sources**, then **OneLake catalog**, and select **TrackTraceEH > TraceEvent**. Select
   **Properties** under **Entity type**, keep all proposed properties, and select **Create**.
1. Repeat with *Scanner Telemetry* and the table **LineScannerTelemetry**.
1. Add the metadata as in part 2:
   - **Trace Event**: Description: *{{onto_te_desc}}* Synonyms: *{{onto_te_syn}}*
   - **Scanner Telemetry**: Description: *{{onto_st_desc}}*
   - **Scanner Telemetry > read_rate_pct**: Description: *{{onto_st_read_rate}}*
   - **Scanner Telemetry > station_mode**: Description: *{{onto_st_station_mode}}*

### Add Line Production Day with the ontology agent

1. Select **Home > Ontology agent** from the ribbon. The agent opens in **Plan** mode. Send:

   > Create a new entity type called Line Production Day, bound to data in the ProductionDaily table from the
   > TrackTraceKPIs semantic model inside this workspace.

1. Toggle to **Act** mode and send *Apply the entity type plan*.
1. Open the details of **Line Production Day** and check that its properties are bound to the semantic model and
   that the **Metrics** section shows **Packs Commissioned**, **Aggregation Error Rate %** and
   **Plan Attainment %**.

> [!NOTE]
> As in part 1: a Fabric data agent doesn't work with an ontology that uses semantic models for binding, and part 5
> removes Line Production Day again for the demo agents. If you go straight to part 5, you can skip this step and
> the measuredOn relationship type.

### Add their relationship types

Select **Home > + Add > Relationship type** for each row. Leave **Use mapping table** off, and select the
property in brackets as **Property 1** on each side. Add the description as relationship metadata.

{{onto_later_rel_table}}

### Link the Scanner degradation rule

In the **Explorer**, expand **Rules**, select **Scanner degradation**, and add **Scanner Telemetry** to its
**Linked ontology elements** next to Production Line.

### Add the inherited entity types (only if the notebook skipped them)

Follow [Add inherited entity type (Distributor)](tutorial-1-create-ontology.md#add-inherited-entity-type-distributor)
in part 1 for Distributor and Hub (from Warehouse) and for Cigarette and Heated Tobacco Stick (from Product).
Then add their descriptions from the table in
[Add entity type metadata](tutorial-2-enrich-ontology.md#add-entity-type-metadata) in part 2.

## Check the result

1. On the canvas, select **Shipment** and switch to the **Neighborhood** view. It connects to Pallet, Factory,
   Warehouse, Partner and Authority Submission.
1. Open the details of **Shipment** and its **Instances** tab. `{{s2_ship}}` has the status **DELAYED**.
1. Open the ontology agent in **Plan** mode and ask:

   > Which shipping cases produced on line PL-02-L3 on {{yday}} have an aggregation mismatch?

   Expect {{s1_cases}} shipping cases, all from production order `{{s1_order}}`.

## What's different from doing parts 1 and 2 by hand

The names, keys, bindings, metadata and rules are the same. A few things are set up the way part 1 recommends
for the graph:

- The relationship types between lakehouse entity types use mapping tables from the start, so in part 3 you
  don't need to add them.
- The entity type keys are already set, so **Prepare the graph** in part 3 is only a check.
- In the definition, each mapping table is its own backing table, named *map_* plus the relationship type name,
  over the lakehouse table from part 1. The inherited entity types have their own backing tables too, for
  example *warehouse_hub*. They read the same lakehouse tables; nothing is copied.

## Run it again or remove it

- If **{{onto_name}}** already has entity types, the notebook stops without changing anything. To rebuild it, set
  `REPLACE_EXISTING = True`. That replaces the whole definition, so you lose the finishing steps and other changes
  you made in the editor, and you need to repeat them.
- To remove the ontology, delete the **{{onto_name}}** item from the workspace, and its graph model if you
  materialized one in part 3.

## Next steps

Your ontology now matches the result of parts 1 and 2. Continue with [Explore the ontology](tutorial-3-explore-ontology.md).
