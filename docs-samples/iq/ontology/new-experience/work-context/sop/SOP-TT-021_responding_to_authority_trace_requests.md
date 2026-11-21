# SOP-TT-021: Responding to authority trace requests

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
