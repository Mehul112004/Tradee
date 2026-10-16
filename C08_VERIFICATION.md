# C08 verification

Verified 16 October 2026 in the dedicated `tradee` Conda environment, Python 3.13.15 on macOS arm64. Both user-requested initial 15m families are implemented: **prior-range breakout and EMA pullback continuation**, with separate strategy identities, causal opportunity inventories, immutable candidates and durable restart. [Contracts](C08_IMPLEMENTATION.md) and [research definitions](C08_RESEARCH_PLAN.md) specify formulas, evidence and ownership boundaries.

## Offline results

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

**350 tests passed in 61.672 seconds:** all 298 previous tests plus **52 new C08 tests**. Ordinary tests use isolated databases without external network, credentials or account access. Existing CI discovery includes these tests; this result is local macOS/Python 3.13 verification, not a claim that remote Linux/Python 3.11 CI was executed.

| Test file | Cases | Evidence |
| --- | ---: | --- |
| [test_c08_strategy.py](tests/test_c08_strategy.py) | 12 | Independent exact range windows/equality/wicks, decimal distinctions, long/short EMA recovery predicates, invalid parameters, separate family/spec hashes, immutable candidate schema and absent invented trade policy |
| [test_c08_engine.py](tests/test_c08_engine.py) | 22 | Full warmup/nontrigger/long/short inventory, actual 15m aggregation, finalized-only input, duplicates, correction diagnostics, per-direction cooldown, gap recovery, stale/expired detection, metadata history/availability/identity/age gates, declared side scope, modeled labels, future-prefix rejection, no suffix leakage, every checkpoint split and real stabilized C03 trend recovery |
| [test_c08_persistence.py](tests/test_c08_persistence.py) | 15 | Actual C01/C02/C03 integration, atomic feature/lineage/inventory/checkpoint rollback, resume/idempotency, direct/persisted parity, pagination, immutable source vintages, metadata timeline, missing/empty coverage, schema/alias/corruption checks, complete inventory counts, full-input completion and consistent summary reads across a real interleaved WAL commit |
| [test_c08_cli.py](tests/test_c08_cli.py) | 2 | Two-family offline catalog/explanation without database creation; JSON errors for missing/aliased stores |
| [test_c08_e2e.py](tests/test_c08_e2e.py) | 1 | 26 real production CLI commands/processes, both default 15m families, independent long/short expectations, full inventories, new-process recovery, source corrections and recorded/modeled availability |

The strategy tests also verify C03's new `ema20_prior`/`ema50_prior` against an independent Decimal recurrence, invariance to the current close, nominal `n+1` warmup and the 396-versus-397 bar stability boundary. Existing C03 formulas/oracles still pass. C03 now exposes 45 named definitions, with its 14-feature baseline unchanged.

## Connected E2E and retained manual demo

```sh
conda run -n tradee python -m scripts.verify_c08 --output data/c08_verification/e2e_consistent
```

The demo imports raw synthetic Binance-shaped metadata and **12120 finalized minute candles** across BTCUSDT/ETHUSDT. Each symbol forms **404 complete 15m bars**. C02's modeled dataset explicitly assumes close-time availability; the C08 policy explicitly labels current metadata as a research assumption. The actual C03 core computes features/aggregation, and the actual C08 CLI/database persists both independent family inventories. Internal components are not mocked.

Independent expected candidates, with zero-based bar indices:

| Family | Symbol | Side | Bar | Exact source reference |
| --- | --- | --- | ---: | ---: |
| Range breakout | BTCUSDT | Long | 402 | 144 |
| Range breakout | ETHUSDT | Short | 402 | 156 |
| Range breakout | BTCUSDT | Short | 403 | 130 |
| Range breakout | ETHUSDT | Long | 403 | 170 |
| Trend continuation | BTCUSDT | Long | 401 | 140 |
| Trend continuation | ETHUSDT | Short | 401 | 160 |

The earlier paths are mirrored gradual trends; bar 400 supplies a pullback, bar 401 recovery and bars 402/403 the independent range breaks. Literal bar/side/price expectations are independent of production trigger functions. No outcome, trade success label or optimization is used.

| Inventory | Evaluations | Emitted | Nontrigger | Rejected | Revision only |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base range | 1616 | 4 | 1532 | 80 | 0 |
| Base trend | 1616 | 2 | 30 | 1584 | 0 |
| Observed metadata applied to modeled historical decisions | 1616 | 0 | 0 | 1616 | 0 |
| New modeled range source vintage | 1616 | 4 | 1532 | 80 | 0 |
| Recorded historical import plus correction | 1618 | 0 | 0 | 1616 | 2 |

Both base families represent all 404 expected buckets per symbol without missing coverage. Trend's 1584 warmup/stabilization rejections and 32 context-ready evaluations expose the substantial seed requirement instead of silently discarding that period.

Verified failure/recovery and evidence paths:

- A real SQLite trigger aborts evaluation writes after the first committed 30-event prefix. The command exits 1 with **four evaluations and one checkpoint** intact. A new CLI process resumes, including nonmonotone modeled event IDs, and reaches the expected final inventory. Feature/lineage/inventory/checkpoint writes are transactional. This is statement-failure recovery, not a physical disk/power-loss drill.
- Completed reruns retain hashes/counts. Inventory pagination returns the next ordered opportunities without dropping a direction. Candidate feature/lineage commands expose the actual C03 prefix.
- Today's metadata cannot authorize earlier observed-mode decisions. The modeled historical run emits only with explicitly selected research assumptions.
- A new modeled vintage changes the corrected BTC short reference from 130 to 131 while preserving the original run/candidate records. Modeled snapshots retain the latest finalized source version by design.
- Recorded replay retains both original and corrected observations. The correction produces two `revision_only` diagnostics and no backdated candidate. Those old historical imports are stale at actual receipt; a fresh signal is not fabricated.

Final base range run: `7e50f76be0a546666de3bc225a78bbc234462a939c9f981e5ddf2192e9bfa516`.

Final base trend run: `4acfa8b64de95c78c99d3bc2ac295c920c1fb50237055cc4016565002690afb2`.

Retained artifacts in `data/c08_verification/e2e_consistent/` are excluded from Git: three component databases, raw inputs, correction, `e2e_commands.json` and `e2e_report.json`. Inspect the base range candidates:

```sh
conda run -n tradee python -m tradee candidates \
  --candidate-db data/c08_verification/e2e_consistent/c08.sqlite3 \
  records 7e50f76be0a546666de3bc225a78bbc234462a939c9f981e5ddf2192e9bfa516 \
  --status emitted
```

Read each candidate's source/feature/metadata hashes, exact reference and exclusive expiry; inspect rejected/warmup pages and missing-coverage fields; repeat a completed command from the log. Use a fresh directory to repeat the complete E2E. The demo ends at setups, with no invented stop/target/size, fill, ledger or trading expectancy.

## Public Binance feed and saved replay

The restricted-network attempt could not reach Binance. The approved public retry captured C01 metadata, enough public BTCUSDT minute history for **400 completed 15m bars**, and **three candle WebSocket messages** using existing adapters. Final verification replayed the saved capture in a new process with a fixed production tree. An intermediate verification invalidated by source changes during development was discarded; source changes correctly create new run identities.

Direct incremental evaluation, persisted replay and completed rerun matched for both families in both modes:

| Mode | Family | Replayed events | Evaluations | Context ready | Emitted |
| --- | --- | ---: | ---: | ---: | ---: |
| Recorded, observed metadata | Range breakout | 6016 | 800 | 0 | 0 |
| Recorded, observed metadata | Trend continuation | 6016 | 800 | 0 | 0 |
| Modeled, metadata research assumption | Range breakout | 6013 | 800 | 760 | 34 |
| Modeled, metadata research assumption | Trend continuation | 6013 | 800 | 8 | 0 |

All four runs represent the 400 complete buckets without missing coverage. Recorded imports preserve actual receipts: older closes are stale for detection, so zero fresh candidates is the correct integration result. Modeled mode selects finalized candles at the declared source vintage, excluding partial WebSocket updates. Only the final four trend bars have enough stable EMA history. Candidate counts are functional observations, not evidence of profitability or a comparison of strategy quality.

- Recorded dataset: `8fca80b978a5f7eea12ec6cf10b69dd3073effe8a178bb4f354732611f811a36`.
- Modeled dataset: `aaa0692b162b3018e9d41b0bfc412e121085357fe5d37ee8ff2b0a2241ffe778`.
- Recorded range run: `14b25753cdd248442b351daa46ec1d8d18d3c4f98a67d672a69eb52d5073f3a0`.
- Recorded trend run: `137317d5381549bd0aba7a9522ccb845f15ed36d5923444106c0736f83d20991`.
- Modeled range run: `d8a4b7dd3464524989cb9d96f0fe53f02196ba570ada58492060272f081ce3a4`.
- Modeled trend run: `843129e80cf1c10a9a26fb5eeef1e01ecc29b7dd7391cd0c41039a99dd6bc9ea`.
- Verified production source-tree hash, also matched by retained E2E manifests: `0db3dddd16a6ab33b3b6818f4f243c6f1a7542c0f7f08749bdbebb7baef81cc9`.

Capture databases, `capture.json` and final `live_report.json` are in `data/c08_verification/public1/`. Replay offline:

```sh
conda run -n tradee python -m scripts.verify_c08_live --replay --output data/c08_verification/public1
```

## Remaining scope

- C09 must specify executable order/stop/target/holding/size/cancellation rules, recheck the setup at action time, own position quantities and book C07 fills/fees plus C06 settled funding once. C08 expiry/reference/trigger context alone cannot establish an executable trade.
- C11/C12 must compare each family independently after costs, against declared no-trade/simple-exposure baselines, with trial accounting and unseen evaluation. Neither family has performance-based promotion or an expectancy estimate.
- Initial presets are intraday 15m. General timeframe configuration is not independent swing validation. More families, horizons and C04/C05/C06 context filters remain separate reviewed upgrades.
- Verified historical metadata and richer execution/market coverage remain data limitations. Modeled close-time and metadata assumptions never become recorded historical evidence.
- Recorded corrections preserve prior decisions; a newly pinned modeled latest-finalized vintage can change hypothetical history. Active-trade correction/cancellation semantics belong to C09/C14.
- The reference engine retains/reconstructs C03 history. The connected test exercises a few days, not multi-year/full-universe throughput, bounded live memory, migration/backup or unattended physical-failure recovery.
- Telegram, dashboard, live scheduling and full signal/outcome measurement remain downstream. No secrets were read, account endpoints called, orders placed or notifications sent.

All remaining work has component IDs, dependencies and completion gates in [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md#c08-candidate-generation). C09 trade policy and outcomes is next.
