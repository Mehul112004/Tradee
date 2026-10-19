# C11 verification

Verified 19 October 2026 in the dedicated `tradee` Conda environment, Python 3.13.15 on macOS arm64. [Research decisions](C11_RESEARCH_PLAN.md) define causal/accounting contracts; [implementation](C11_IMPLEMENTATION.md) describes operation and limits.

## Regression results

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

**448 tests passed in 119.791 seconds:** all 404 prior component tests plus **44 new C11 tests**. This final full run overlapped the separate saved-public replay and retained CLI demo on the local machine; it is a measured regression result, not a throughput benchmark. Offline discovery uses isolated stores and no network, credentials or account operations. CI already discovers these tests on Python 3.11/3.13; remote CI was not run here. Compilation with `python -m compileall -q tradee scripts tests` and whitespace checks also passed.

| Test file | Cases | Evidence |
| --- | ---: | --- |
| [test_c11_contracts.py](tests/test_c11_contracts.py) | 6 | Strict versions/fields, explicit positive size and horizon, bounded windows/resources, duplicate scenarios, metadata disagreement, missing trigger/product evidence and fee/input validation even with no candidates |
| [test_c11_engine.py](tests/test_c11_engine.py) | 19 | Real C08/C03/C07/C06/C09 golden long/short/partial ledgers; first-known outcome times; warm-up and half-open boundaries; no pre-detection exposure; same-time source/sample order; fresh/stale marks; exact gap timers/expiry/timeout; unknown funding/open tails; funding corrections and maturity revocation; future-price independence of earlier candidates; streaming/chunked parity; changed/missing source failure; explicit resource failure; both families and horizons; modeled close versus conflicting range ambiguity |
| [test_c11_analysis.py](tests/test_c11_analysis.py) | 7 | Empty/unknown denominators, mature-only coverage and empirical tails, exact shortfall attribution without double charge, corrupted ledger rejection, regular mark drawdown/null missing samples ambient Decimal-context independence, cached canonical digest equality and read-only/document-copy isolation |
| [test_c11_persistence.py](tests/test_c11_persistence.py) | 8 | Immutable full artifacts, stable pagination, one-transaction rollback and deterministic retry, missing/corrupt evidence, wrong stores/aliases, incomplete/conflicting results, matched fee/delay comparison and rejection of unmatched experiments |
| [test_c11_cli.py](tests/test_c11_cli.py) | 3 | Offline no-database explanation, JSON errors/missing or aliased sources, valid shipped two-family presets |
| [test_c11_e2e.py](tests/test_c11_e2e.py) | 1 | Actual raw-import CLI processes through stabilized features, both hypothesis families/directions, exact ledgers, publication failure/retry, causal revisions, regular marks, sensitivity, unknown funding, delay and immutable source vintage |

Literal expected monetary values are written independently of production P&L functions. Tests inspect ledger quantities, recognition times, source prefixes and missing coverage in addition to exit codes. All prior indicator/oracle and component integration tests still pass.

## Retained CLI E2E for manual review

```sh
conda run -n tradee python -m scripts.verify_c11 --output data/c11_verification/e2e_verified
```

**19 real CLI commands/processes passed**, starting with synthetic Binance-shaped metadata, 804 raw closed minute candles (402 per symbol), entry quote/mark messages and exit quote/mark/contract-trade messages. Actual C03 computations stabilize EMA20/EMA50 and their prior values; C08 emits one fresh range and one trend candidate for each symbol. Earlier imported bars remain causal warm-up/diagnostics with their actual receipt times. No production component is mocked.

Explicit fixture assumptions: 1m strategies, two-bar prior range, fixed 1% stop / 2R target, one base unit per independent scenario, zero manual entry delay, 25bps spread gate, synthetic rules and declared empty settlement calendars. These differ deliberately from the illustrative 15m/default-delay presets and are not optimized settings or Binance account evidence.

Per family:

| Item | BTC long | ETH short |
| --- | ---: | ---: |
| Candidate reference | 142 | 158 |
| Entry / exit fill | 142.2 / 145.8 | 157.8 / 153.2 |
| Gross USDT | 3.6 | 4.6 |
| Fill fees USDT | 0.144 | 0.1555 |
| Funding under fixture calendar | 0 | 0 |
| Net USDT | **3.456** | **4.4445** |

Both families therefore produce four independent closed/mature trades, **16.4 gross − 0.599 fees = 15.801 USDT**. Each position ends flat with two fill entries. These are independent scenario sums; they are not a funded combined portfolio. The retained baseline has 3,216 candidate diagnostics, 1,608 feature artifacts, 1,608 lineage artifacts, two lifecycle manifests, 16 transitions, 16 outcome revisions and 879 sample artifacts (293 timestamps × two scenarios plus their diagnostic sum). Grid/sample counts can vary with real import receipt times on another run.

Checks with retained evidence:

- A real SQLite trigger aborts report insertion after artifact inserts. The entire transaction rolls back: no run, report or artifact remains. A new CLI process deterministically rebuilds the run and publishes exact ledgers. This tests statement/transaction failure, not power-loss durability.
- Completed reruns return identical hashes and amounts after validating artifact inventory. Later source imports cannot rewrite the pinned run.
- Doubling the assumed taker fee to 0.001 preserves four matched mature candidates and changes their total net by exactly **−0.599 USDT**. The compare command freezes both reports and reports coverage changes separately.
- Omitting calendars saves four closed but unresolved net outcomes, with null total net and exit 2. Explicit manual delay produces no retroactive entry; its short tail remains unresolved and exit 2.
- Mature revision artifacts record when the outcome first became usable, not just when the trade exited. Direct fixtures additionally prove nonzero funding revision replacement, first-known correction times and revocation on subsequently observed boundary ambiguity.
- The retained 100ms fixture grid has complete valuation coverage at its sample times; it can miss brief exposures/moves between samples. Direct fixtures verify exact open mark P&L, a nonzero regular drawdown and that a stale/missing mark makes full drawdown unknown. No percentage/Sharpe/annualization claim is made.

Retained baseline run: `6f20ebcaa53b449adb5e465dbf4cae6b8bc1108f86a715ace09fd8e65e7bdf2b`.

Retained baseline report: `f7f7221805dc1f1b9554617144a779a4d000ccb8343fc05e25e1a3ce4bdef01a`.

The ignored directory retains raw JSON/JSONL, all config variants, C01/C02/C11 SQLite databases, `e2e_report.json` and `e2e_commands.json`. Inspect it via the production CLI using the explicit database paths, for example:

```sh
python -m tradee --db data/c11_verification/e2e_verified/c01.sqlite3 simulate \
  --market-db data/c11_verification/e2e_verified/c02.sqlite3 \
  --simulation-db data/c11_verification/e2e_verified/c11.sqlite3 summary \
  6f20ebcaa53b449adb5e465dbf4cae6b8bc1108f86a715ace09fd8e65e7bdf2b
```

## Public data and validation boundaries

The saved-public replay is separate from ordinary offline test discovery. Its script reuses the retained C08 public Binance candle capture through both C08 families and the C11 runner, without a new network request:

```sh
conda run -n tradee python -m scripts.verify_c11_public_replay \
  --source data/c08_verification/public1 --output data/c11_verification/public1
```

This explicitly modeled dataset cannot establish historical quote/trade fills, continuous trigger paths or certified settled funding. Current metadata, close availability, bar mark proxy, fee and quantity assumptions are pinned. Modeled net/profit labels must remain null. The final public replay **passed** on dataset `aaa0692b162b3018e9d41b0bfc412e121085357fe5d37ee8ff2b0a2241ffe778`:

- All **6,013 source candles** replayed through both full passes with identical source count/cursor/prefix; two detectors produced **1,600 direction diagnostics** and **800 feature artifacts** across 400 complete 15m bars.
- Range breakout emitted **34 candidates**, all filled and closed through the shared lifecycle; the default trend family emitted **zero**. Only eight trend direction evaluations met stable-history requirements and none triggered. Zero trend trades is retained honestly, rather than forcing activity; synthetic E2E separately exercises that family.
- Gross fill-price P&L was **−3.919 USDT**, with **2.8048373 USDT** simulated fees under the declared assumptions. All **34 net outcomes remain unresolved/null** because modeled candle data has no certified settled funding. Mature expectancy, win fraction and portfolio performance are not inferred from these amounts.
- **578 transitions**, **102 causal outcome revisions** and **18,042 sample artifacts** were retained. The combined diagnostic grid has 6,014 points, 5,503 with incomplete valuation evidence; full drawdown and all annualized/portfolio metrics correctly remain null.
- The store verified reconciled ledgers and an identical cached rerun. No source download, account endpoint or notification was used.

Run: `95ad985b4901144a4b4040c23cd8f3b28b68884dffb1e4f2756b9c3be8332878`.

Report: `153a47367494676ba743633d30148ca47416641489f0f98ce2b5db39a47857c4`.

Retained evidence: `data/c11_verification/public1/public_replay.json` and its C11 database. Code hash for both final demos: `978a7c753746376e94baf95edffbaec639d067184c8963fc0b70a4e340aaefd2`.

The first broad replay exposed repeated digest computation over the **927-instrument** pinned metadata universe. It was interrupted for a targeted fix: cache immutable record digests behind the existing read-only property, retaining canonical hash values and independent document copies. Final regression, CLI E2E and public replay were rerun after that change. This removes the observed redundant-hashing bottleneck; it does not certify multi-year/universe throughput or remove the remaining C03/C11 scale upgrades.

No profitability, sufficient independent sample size, confidence interval, walk-forward holdout, finite-capital/margin/liquidation, physical recovery or unattended live operation is certified by these fixtures. C10/C12/C13 and the operational/fidelity work in [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md) retain those requirements. No account keys, orders or Telegram messages were used.
