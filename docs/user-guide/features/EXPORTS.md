# Exports and evidence identity

**Access:** viewer for available, unlocked evidence. Downloads do not start research, send a message or change a component store. They preserve the scope and limitations of the selected source.

## Available exports

| Export | Where / how | Scope |
| --- | --- | --- |
| Signal CSV | Signals → Export CSV | Latest selected session's ledger; identifiers, symbol/side, phase/times and delivery state |
| Session JSON | `/api/WORKSPACE/sessions/SESSION_NAME/export?format=json` | Latest verified/redacted session evidence |
| Independent simulation JSON | Research → Run inspection → download | The inspected stored simulation result; independent-candidate scope |
| Source artifact JSON | Supported `/api/WORKSPACE/artifacts/COMPONENT/HASH?download=true` route | The requested verified artifact, subject to access/holdout guards |
| Mature forward dataset | C15 CLI `monitor export` | Mature rows from an explicitly identified report vintage, with separate tracks and source identity |

Use full actual IDs and the API origin currently serving your workspace. The uppercase URL segments are placeholders, not clickable destinations. The session CSV endpoint also accepts `format=csv`.

## Historical scope matters

The current session export endpoint has **no historical-cursor argument**. The Signals button and session JSON export use latest state even while a screen shows an earlier replay cursor. Passing `at_ms` to that export does not turn it into a historical download. Record the source scope and use pinned artifact/report identities for an earlier investigation.

CSV is a compact ledger, not a complete numeric/performance report. For exact financial evidence, inspect the JSON documents/ledgers; chart formatting rounds for display. CSV cells beginning with spreadsheet formula characters are escaped. Exports are redacted, but still contain trading metadata and numeric destination identifiers where retained—review before sharing.

## Export a pinned forward vintage

```sh
conda activate tradee
python -m tradee monitor export MONITOR_NAME --report REPORT_HASH
```

You can redirect this JSON to an ignored local file if needed. Use the matching custom C15 store for a custom workspace. Earlier reports retain earlier maturity status; an old pending row must not acquire a later label in that old report. Exported independent rows and portfolio rows cannot be summed as one wallet.

## Limits

Holdout protection also applies to evidence routes; lack of export access is not permission to open the final period casually. Forward exports are future-research inputs, not automatic C10 training imports or fresh untouched holdouts. Chart images, universal one-click bundles and richer report exports remain future UI work.

Related: [historical replay](HISTORICAL_REPLAY.md), [research](WALK_FORWARD_RESEARCH.md), [upgrade register](../../platform/COMPONENT_UPGRADES.md).
