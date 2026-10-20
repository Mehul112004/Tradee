# C09 trade lifecycle and outcomes

C09 implements independent **paper trade lifecycles** from evidence-bound C08 candidates. It requests admitted C07 entry/exit fills, owns resulting quantities, reconciles C06 settled funding once, and produces immutable policy-specific outcomes. [Research decisions](C09_RESEARCH_PLAN.md) explain the initial rules; [verification](C09_VERIFICATION.md) records actual tests. A paper fill remains a model scenario, not an exchange order or confirmed account transaction.

## Components and files

| File | Main responsibility | Dependencies and consumers |
| --- | --- | --- |
| `tradee/c09/contracts.py` | `TradePolicy`, immutable `TradeIntent` evidence, fixed levels and `LifecycleRecord` | C08 `CandidateSpec`, C03 snapshot, C01/C02 validation; consumed by lifecycle/runner |
| `tradee/c09/engine.py` | Shared event/time state machine, exact candidate activation, thesis checks, stop/target/partial/time/invalidation routing, C07 execution, C06 exposure and checkpoints | C01/C02/C03/C06/C07/C08; C11/C14 will drive the same engine |
| `tradee/c09/ledger.py` | Keyed current-value ledger, exact realized gross/net, fee/funding ownership, risk/R, sampled excursions and label maturity | C07 fills and C06 settled records; supplies C10/C11/C12/C15 |
| `tradee/c09/store.py` | Separate C09 SQLite manifests/transitions/reports and atomic checkpoint recovery | Shared engine and C02 replay; standalone CLI reference driver |
| `tradee/c09/cli.py` | Explain/run/manifest/summary/report/transition | Explicit intent, fee, execution and funding inputs |
| `configs/c09_trade_policy.json` | 1% fixed stop, 2R target, four-hour limit, contract-trade triggers | Defaults frozen before performance research |
| `configs/c09_bar_policy.json` | Same levels with completed-bar-close trigger | Explicit coarse historical alternative |
| `scripts/verify_c09.py` | Actual-process raw import → C08 → C07/C06 → C09 E2E | Reviewable synthetic long/short ledgers, null-coverage and delay cases |
| `scripts/verify_c09_public_replay.py` | Retained public Binance candle replay | Explicit modeled availability/current rules/mark proxies; no new network session |

C09 takes caller-supplied quantities. It does not choose portfolio risk, claim leverage/account validity, implement automated exchange orders, select strategies or estimate expectancy. C11 remains the full historical simulator/orchestrator, including broad history, inventory reconciliation, experiments and attribution; C12 owns research validation and promotion.

## Frozen intent and outcome policy

A `TradeIntent` contains the complete candidate, its actual feature snapshot with hash, positive base quantity and explicit `TradePolicy`. Candidate/snapshot identities, timeframe/target, detection, input cursor/prefix and usable time must match. Both must belong to the same pinned C02 dataset. A stable trade ID hashes candidate ID, policy hash and requested quantity.

The default policy uses:

- Stop distance `d = reference_price × 0.01`.
- Long stop `reference − d`, target `reference + 2d`; short reverses the signs.
- Four-hour maximum hold measured from actual entry.
- Optional partial target at a declared R below the final target; default fraction 0.5 of original filled size when enabled.
- Contract-trade trigger source, 5000ms strict trigger freshness, 60000ms maximum sampled-path gap.
- Explicit zero exit delay and 60000ms exclusive exit-request wait budget. Entry keeps the configured C07 processing/delivery/manual delay, normally 30 seconds.

All levels are frozen from detection-time reference, rather than adjusted after slippage. Initial risk used for reported R is **absolute actual-entry-to-fixed-stop distance × actual initial quantity**. The target can therefore represent a different realized R after entry costs. Prices, quantities, fees, ledger amounts and risk use exact decimal arithmetic; ratios alone use C07's documented 12-decimal diagnostic rounding.

No trailing stop, breakeven move, scale-in or automatic stop relocation follows a partial. Changing policy parameters changes the trade/run identity. Neither family receives a success probability or optimized policy.

## Lifecycle and event ordering

```text
waiting → pending_entry → open → exit_pending → closed
              |             |         |
          expired or        +---------+→ unresolved when evidence/execution fails
          cancelled
```

`waiting` means the candidate's exact known source prefix has not arrived. The engine verifies cursor and prefix hash before activation; a foreign/corrupted prefix fails. Future candidates in the pinned input list cannot authorize an earlier fill.

For pending entry:

1. Respect C07's earliest action time and the candidate's exclusive expiry.
2. Require current valid/stable C03 context, fresh for the candidate timeframe.
3. For range breakout, current completed close must remain beyond the original boundary. For trend, fast/slow direction and the close's recovered side must remain valid; do not require a new recovery crossing at every retry.
4. Request a C07 market estimate using already available quote/mark/rule/fee evidence. Rejections remain pending rather than becoming fills.
5. Reject an admitted price already beyond the fixed final target. C07 separately rejects an entry through its stop or outside its budgets.
6. Book the admitted quantity/price/fee once and begin the holding clock.

For modeled bars, C09 requires the entry price bar to start at/after detection. It therefore does not reuse the already completed candidate bar as an entry. The first full later minute must fit inside the entry window. A one-minute candidate with only a one-minute exclusive window may consequently remain unfilled; the initial 15m/five-minute presets leave room for a later minute.

Triggers never substitute their threshold into C07's execution price. An eligible quote must be available at/after the action/request time, and C07 separately enforces economic quote/mark freshness. This preserves receipt semantics when an exchange timestamp precedes local processing by a few milliseconds.

Only one quantity change per trade/millisecond is allowed. Entry and exit cannot occur in the same logical millisecond. Multiple independent trades can exist at that time because shared capital/book consumption is outside this component.

## Stops, targets, partials and gaps

Supported trigger sources are explicit:

| Source | Trigger evidence | Execution evidence |
| --- | --- | --- |
| `contract_trade` | Normalized C02 contract trade price | C07 recorded quote and mark |
| `mark` | Normalized mark-price observation | C07 recorded quote and mark; mark itself is not a fill |
| `bar_close` | Finalized minute close only | C07 explicit completed-bar close scenario, or available recorded quote in recorded mode |
| `bar_range` | Full finalized minute low/high after entry | Same C07 execution model; touch ordering can be unresolved |

Default targets are market-close requests, not passive take-profit limit orders. C07 applies taker fees. A gap through a stop can fill at a worse available quote; no stop-price guarantee is invented. If a recorded mark/trade is stale or arrives after a newer economic trigger, it cannot rewrite prior fills. The path is flagged incomplete/late and the profit label remains unresolved.

Stop has priority over time exit on the same observation. A final target has priority over a partial when one observation jumps through both. Once a full exit request is latched, later recovery does not silently cancel it. A stop/full close can replace an unfilled partial. Requests retry against C07 within their deadline; spread, liquidity, metadata or fee failures retain the remaining quantity. Timeout produces `unresolved`, never a fake flat position. Time-exit deadlines are anchored to the original holding-limit time, even if the driver notices late.

For partials, proposed size is initial filled quantity × fraction, floored to the common C07 lot grid and rechecked. It cannot exceed remaining quantity. A zero/dust/unexecutable partial is not rounded up; it is flagged, skipped, and leaves exposure intact. Any remaining size must eventually close or remain unresolved.

`bar_range` cannot order a stop and target/partial touched in the same bar. It records `stop_and_target_same_bar`, keeps quantity/fees as known, and stops inventing later path-dependent fills. For a single range trigger, the model requests execution **after bar completion at the available close**, not at an invented intrabar threshold. That delayed-close scenario is not a conservative bound on all possible intrabar fills. The default candle preset uses close-only decisions to define this latency explicitly. Finer path evidence or a separately validated fill policy is future work.

Bars overlapping the entry instant are excluded from range excursions/triggers to avoid importing pre-entry highs/lows. Missing bar continuity or long sampled event gaps add ambiguity flags. Excursions are sampled diagnostics, not certified continuous extrema.

## Invalidation and terminal states

Pending setup loss cancels entry. An explicit `cancel(trade_id, when, reason)` API action cancels a pending entry or requests a full market exit from an open position. It respects the known clock and records resulting state. The CLI replay consumes pinned market/intents; it does not inject operator actions. A C14 command journal must persist external cancellation actions for reproducible forward operation.

`expired` and `cancelled` before entry are valid unfilled outcomes. `unresolved` can mean exit failure, conflicting bar path or another missing path condition; quantities remain visible. At the dataset tail, waiting/pending/open/exit-pending states get `unresolved_data_tail`. No open trade is silently force-closed at the final candle or counted as a loss.

C07's current metadata/allowlist gates apply to exits too. A disabled/nontrading instrument can block a model close. Emergency/account-specific exit routing needs its own reviewed policy; this implementation does not bypass rule evidence.

## Ledger and funding ownership

Each fill key has one immutable executed revision. Entry books its fee; each partial/full exit books signed fill-price gross P&L and its own fee. A conflicting revision of an already booked fill fails. C07 execution estimates—including next-settlement projections—remain in attempt evidence and cannot become extra ledger costs.

```text
long gross = Σ exit_quantity × (exit_fill − entry_fill)
short gross = Σ exit_quantity × (entry_fill − exit_fill)
net = gross − sum(fill fees) + signed settled funding
R denominator = initial_quantity × |actual_entry_fill − fixed_stop|
```

Spread, drift, slippage and tick effects are already in fill prices. Subtracting C07 implementation shortfall again would double-charge them. Fees are charged once per actual simulated fill, including partials.

C09 creates a C06 `PositionTimeline` from resulting quantities: initial exposure, each partial remainder, final zero. C06 uses quantity at settlement with its strict boundary policy. The funding report window includes the declared boundary guard around entry/exit so a settlement just before entry is not silently ignored. Nominal boundaries remain an explicit C06 sensitivity policy.

Each settlement has a stable cash-flow key. The current ledger value replaces its previous amount/revision; a revised source does not add a second full charge. Missing schedules, missing rates and strict boundary ambiguity keep total funding/net null. Known funding and realized gross/fees remain available as a **subtotal**, not a certified net outcome.

A complete funding total is conditional on a caller-declared calendar covering the exposure/report interval; an empty list of expected settlements is an explicit no-settlement assumption, not automatic historical certification. C02 modeled datasets remain candle-only, so modeled funding stays unsupported/null instead of importing eventual settled rates as earlier context. Recorded C02 funding history can resolve outcomes at its actual later recognition time.

## Labels, risk and knowledge time

Outcome reports expose lifecycle status/remaining size, entry/exit and holding times, gross/fees/funding/net, gross/net R, sampled MFE/MAE prices and R, source ambiguity, policy identity and label interval.

`target_before_stop` describes the first observed final target versus stop trigger. `profitable` describes **net USDT > 0** only when the trade is closed, funding is complete under its declared calendar, path flags are clear and the report marks its consumed prefix complete. They are different labels: a target-first trade can lose after fees. Partial-target touches are not substituted for the final-target label.

A mature outcome has a revision hash and `outcome_known_ms`. Repeating the same mature ledger does not move its recognition timestamp. A funding revision changes the outcome revision and its recognition time; older reports remain immutable. Ordinary intermediate reports remain provisional. A fixed-prefix report does not assert that no future provider correction will arrive.

Missing/ambiguous data produces null net-profit labels and `label_status=unresolved`. A numeric conditional gross/net amount, when available alongside path flags, is not a mature training label. C12 must select only outcomes known before its fit/selection time and preserve unresolved counts.

## Persistence, CLI and evidence inputs

Separate `data/c09.sqlite3` uses application C09/schema 1. Manifests pin all intent/candidate/feature evidence, execution/fee/funding policies, calendars, C01 snapshots/versions, C03 config/definitions, C02 vintage, Python version and production source hash. Transitions, report and checkpoint commit together. Quantity conservation, executed-fill evidence, ledger arithmetic, feature hashes and shared child prefix are checked on restore.

Each report contains current keyed ledger/state, while transitions preserve lifecycle changes and execution attempts. Funding reconciliation appears in subsequent report/checkpoint state; it is not a second executed fill. A complete checkpoint requires all pinned source events to have been consumed. Reruns resume exactly and do not repeat fills/fees. Operational wall time is outside deterministic hashes.

The minimal intent file is:

```json
{"schema_version":1,"intents":[{
  "candidate": {"...":"complete emitted C08 candidate"},
  "feature_snapshot": {"...":"complete C08 feature command result with snapshot_hash"},
  "quantity":"0.001",
  "policy": {"version":1,"stop_fraction":"0.01","target_r":"2","max_holding_ms":14400000,"trigger_source":"contract_trade"}
}]}
```

The placeholder objects illustrate the schema; use complete actual artifacts. The E2E script generates runnable bound files. Each candidate and feature must come from the same dataset passed to lifecycle run. Fee and calendar formats remain C07/C06 contracts.

```sh
conda activate tradee
python -m tradee lifecycle explain
python -m tradee --db data/c01.sqlite3 lifecycle \
  --market-db data/c02.sqlite3 --lifecycle-db data/c09.sqlite3 \
  run DATASET_HASH --intents intents.json --fees configs/c07_fee_assumptions.json \
  --execution configs/c07_execution.json --funding configs/c06_funding.json \
  --calendar calendar.json
python -m tradee lifecycle summary RUN_HASH
python -m tradee lifecycle manifest RUN_HASH
python -m tradee lifecycle report REPORT_HASH
python -m tradee lifecycle transition TRANSITION_HASH
```

Database options precede the action. `--batch-size` controls checkpoint frequency. Exit **0** means the saved final report is ready (mature trades or valid unfilled outcomes); **2** means saved unresolved outcomes; **1** means input/operational failure. Database replay completion and outcome maturity are separate fields. No API key, account permission or network connection is required by the lifecycle CLI.

## E2E and manual verification

```sh
conda run -n tradee python -m unittest tests.test_c09_e2e -v
conda run -n tradee python -m scripts.verify_c09 --output data/c09_checks/demo1
```

Use a fresh directory. The script imports raw synthetic BTC/ETH metadata/candles/quote/mark/trades with actual receipt times; computes real C08 candidates and C03 evidence; requests C07 fills; supplies an explicit empty synthetic settlement calendar to C06; and persists exact long/short C09 outcomes through actual CLI processes. It injects a real database statement failure after the first committed batch, resumes in another process, and checks idempotency, unknown funding, entry delay and immutable old data.

The fixture explicitly uses zero entry delay and a 25bps spread gate; it does not alter the default 30-second delay or claim calibrated costs. Expected long net is **2.4965 USDT** and short net **2.5035 USDT**, with two fills/fees each. Read `e2e_report.json`, raw files/configs and `e2e_commands.json`; inspect run/report hashes and exact ledgers; compare delayed/unknown-funding reports for null mature labels. Stops, partials, funding corrections, gaps, ambiguity and time exits additionally have independent unit/integration fixtures.

```sh
conda run -n tradee python -m scripts.verify_c09_public_replay \
  --source data/c08_verification/public1 --output data/c09_checks/public_replay
```

This optional check reuses the retained public Binance C08 candle capture. It adds no fresh live-feed claim. It derives a real range candidate, evaluates a synthetic 0.001-unit lifecycle under explicitly modeled close-time/current-metadata/mark assumptions, and compares direct and persisted reports. Funding remains null without historical coverage. [Verification](C09_VERIFICATION.md) records actual counts/hashes/results. [The upgrade register](../../platform/COMPONENT_UPGRADES.md#c09-trade-policy-and-outcomes) tracks full simulation, action journals, alternate exits, execution fidelity, account effects and scale.
