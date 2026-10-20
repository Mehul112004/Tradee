# C10 verification

Verified 19 October 2026 in the dedicated `tradee` Conda environment, Python 3.13.15 on macOS arm64. [Research decisions](C10_RESEARCH_PLAN.md) explain the estimand and time-block assumptions; [implementation](C10_IMPLEMENTATION.md) defines operator commands and remaining scope.

## Offline regression

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

**502 tests passed in 148.511 seconds:** all 448 previous component tests plus 54 new C10 tests. This final regression overlapped the retained E2E/public-evidence checks on the local machine.

C10 adds **54 tests**. Ordinary discovery uses isolated stores and no network, credentials or account operations. Existing CI discovery covers these files on Python 3.11/3.13, but remote CI was not executed here. Compilation and whitespace checks also pass; the final measured result above is local verification, not a performance benchmark.

| File | Cases | Evidence |
| --- | ---: | --- |
| [test_c10_contracts.py](../../../tests/test_c10_contracts.py) | 5 | Strict windows, schema/fraction/budget/default configuration, complete current inference evidence, strategy compatibility and rejection of disabled directions |
| [test_c10_statistics.py](../../../tests/test_c10_statistics.py) | 13 | Literal mean/payoff/tail/frequency values, independent seeded bootstrap oracle, circular wrapping/truncation, contemporaneous grouping and trade weighting, sparse/degenerate/empty evidence, coverage, overlap span/resource gates, Decimal-context independence and no invented frequency interval for an unobserved class |
| [test_c10_source.py](../../../tests/test_c10_source.py) | 10 | Exact C11 candidate/feature/revision joins and risk; duplicate run deduplication; strict cutoff/no final-label leakage; unchanged earlier selection under changed future prices; disjoint/overlapping/missing scopes; funding corrections/revocation; unknown funding; corrupted source/resource limits; dataset/funding-evidence provenance |
| [test_c10_engine.py](../../../tests/test_c10_engine.py) | 16 | Frozen applicable/eligible results, no inference-time training, publication/strict training/freshness gates, rejection of training-candidate reuse and changed costs/policies/size/features, sparse/no-fallback and lower-bound abstention, unseen mature symbol, model integrity, deterministic fit, frozen later evaluation and future-label invariance, global resource accounting including empty draws |
| [test_c10_persistence.py](../../../tests/test_c10_persistence.py) | 7 | Atomic fit/snapshot/publication, real versus modeled availability, idempotence, SQL rollback/retry, corruption/aliases/unknown records, immutable inference/evaluation and saved insufficient-evidence models |
| [test_c10_cli.py](../../../tests/test_c10_cli.py) | 2 | Offline explanation without database creation and JSON errors for missing/aliased sources |
| [test_c10_e2e.py](../../../tests/test_c10_e2e.py) | 1 | Raw synthetic receipts through real components, default-threshold earlier fit, actual CLI publication failure/retry, frozen later inference/scoring, honest unknown-label and incompatible-cost abstention |

Money expectations and the small-bootstrap oracle do not call production expectancy/statistics functions to derive their expected answers. Tests inspect causality, quantity/risk/label provenance, coverage and artifact invariance in addition to process status. All prior component formula/oracle tests remain part of discovery.

## Retained earlier-to-later E2E

```sh
conda run -n tradee python -m scripts.verify_c10 --output data/c10_verification/e2e_release
```

**17 actual CLI commands/processes passed**, after raw Binance-shaped metadata/candle/mark/quote/contract-trade ingestion through production C01/C02 APIs. Historical receipt clocks are explicitly injected synthetic evidence, not claimed live capture. C03/C08/C07/C06/C09/C11 are real production implementations; no fill, P&L, label, feature or estimator is mocked.

Training uses 36 daily synthetic sessions, each with four closed minute candles. Gaps between sessions deliberately reset causal feature/range history. This is not a continuous 24-hour market-history fixture. Each session produces one long setup and real paper fills. Inputs declare a 1m/two-bar range, one base unit, zero manual delay, a 25bps spread gate, assumed taker fees and an empty synthetic settlement calendar. These are engineering assumptions, not Binance account/history evidence.

The demo uses the **default C10 configuration**, including 30 mature trades, 20 occupied bins, 10 occupied spans, daily bins, three-bin circular blocks, 2,000 replicates, 95% central percentiles and the fixed seed. Its 36 mature outcomes occupy 36 bins / 12 nonoverlapping spans with complete fixture fill/maturity coverage. Four separate later daily sessions are then scored from the frozen artifact.

Literal per-trade accounting alternates:

| Item | First type | Second type |
| --- | ---: | ---: |
| Candidate reference / actual entry | 102 / 102.2 | 102 / 102.2 |
| Exit fill | 104.8 | 105.8 |
| Gross USDT | 2.6 | 3.6 |
| Entry + exit fees | 0.1035 | 0.104 |
| Funding under fixture calendar | 0 | 0 |
| Net USDT | 2.4965 | 3.496 |
| Actual initial risk USDT | 1.22 | 1.22 |
| Net R | 2.046311475410 | 2.865573770492 |

The earlier fit's mean is **2.455942622951 net R**, with mean net **2.99625 USDT**. Its seeded mean-R interval is **[2.387670765028, 2.524214480874]**. All 2,000 resamples contain observations. Every fixture trade is positive, so empirical frequency is 1 and frequency confidence bounds remain **null**: C10 does not manufacture certainty about an unobserved loss class. Mean-R bounds remain conditional on the declared resampling assumptions and cannot account for unseen outcomes/regimes.

All four later predictions are applicable and eligible under the explicit research gate, then join four mature labels. Later mean R is 2.455942622951; squared net-R prediction error is 0.167797677036. Brier score is 0 on this all-positive fixture and its reliability bucket has four observations. These are arithmetic diagnostics, **not evidence of calibration, edge or generalization**. Separate tests change future prices/outcomes while keeping frozen predictions unchanged.

Additional retained checks:

- An actual SQLite trigger aborts model insertion after snapshot/fit writes. The entire transaction rolls back; a new CLI process rebuilds and publishes. This is statement/transaction recovery, not power-loss durability.
- Repeating the fit reuses exactly the model, fit, snapshot and availability identity. Later evaluations leave the earlier artifact unchanged.
- The later C11 run without calendars yields four predictions but zero matched mature labels. Evaluation errors remain null and exit 2; fitting those unknown outcomes also saves an insufficient-evidence artifact and exits 2.
- A changed taker fee request abstains with an incompatible-protocol reason. Future/stale publications, disabled directions, nonmatching features, training-candidate reuse and low-coverage/degenerate cohorts have direct tests.
- Work-limit tests count empty resampling draws as work and reject oversized results without publishing a partial estimator.

Retained model: `a6387fd588945815f087586139d0c0c96185d268404b7bd89628a7b51031034e`.

Fit: `e598f98f15c254870cb9510a57d726ef4268e50b57b165ad638abfebabab774e`.

Training snapshot: `76a948be76dc15e6d7b35506659ad497fa50d1bc84fbda944d44054abc9e8368`.

Later evaluation: `3645f912f80947bc1711a837c11d540ec9ba8dac315ce6bf5cb632ef124a37f8`.

Final fit code hash: `343ae55777dbe73cbe101009e2b40e53956afe67516457173fc3f348579a1eab`.

The ignored directory retains raw receipt JSONL, metadata/config/window JSON, the full inference request, all C01/C02/C11/C10 SQLite stores, `e2e_report.json` and `e2e_commands.json`. Inspect through `expectancy model`, `training-snapshot`, `fitted`, `estimate-record` and `evaluation`, supplying the custom C10/C11 paths.

## Saved public evidence: honest insufficiency

```sh
conda run -n tradee python -m scripts.verify_c10_public_evidence \
  --source data/c11_verification/public1 --output data/c10_verification/public1
```

This check **passed**, reusing the saved C11 replay of 6,013 real Binance candles. That source has 34 closed range-breakout scenarios but **no certified settled funding/net labels** under its explicitly modeled availability/metadata/execution assumptions. C10 retains all 34 as unresolved, creates four declared protocol/direction cohorts, reports zero mature training targets, keeps all mean/interval values null and publishes `ready=false`. Repeating the publication is idempotent. No network call or fabricated label is involved.

Retained insufficient-evidence model: `40c9331dce95e73f656dca51c5a34dbb2304b84a0d09e7bcdefac77fb1c09bba`.

Source C11 run: `95ad985b4901144a4b4040c23cd8f3b28b68884dffb1e4f2756b9c3be8332878`.

Retained artifact: `data/c10_verification/public1/public_evidence.json`, with its C10 database. Public data presence alone is not sufficient evidence for a usable expectancy estimator.

## Validation boundaries

This completes the initial C10 statistical/software scope. Whether these strategies or the complete eligibility policy improve untouched later real outcomes remains unproven and belongs to C12/C13 research. Source-window scope coverage is not continuous feed certification; internal market-data gaps, representativeness and selection bias still require C02/C11/C12 quality controls. Empirical frequencies are not calibrated probabilities; block/gating choices are not validated power or interval-coverage guarantees.

Predictive models, shrinkage/context, advanced dependence/heavy-tail methods, protocol/release adapters, migrations/backup/large-history benchmarks, C11/C13 policy injection and C14/C15 runtime refresh/monitoring remain in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md). No authenticated account access, orders or Telegram messages were used.
