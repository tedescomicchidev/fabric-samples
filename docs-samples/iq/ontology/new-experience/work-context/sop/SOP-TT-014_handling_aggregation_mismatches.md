# SOP-TT-014: Handling aggregation mismatches

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
