# C13 — shared portfolio risk and allocation

Implemented 20 October 2026 for Binance USDT perpetual research. C13 converts individually eligible setups into a deterministic funded paper book. Its policy is shared by the offline portfolio runner and local account proposals. C14 owns eventual live orchestration and delivery. See [operation](C13_IMPLEMENTATION.md), [verification](C13_VERIFICATION.md) and [remaining scope](COMPONENT_UPGRADES.md#c13-portfolio-and-alert-selection).

## Dependencies and consumers

| Component/input | What C13 receives | Where used |
| --- | --- | --- |
| C01, through C11/C07 | Instrument identity, observed rules, universe snapshots and metadata versions | Exact-size execution eligibility, identity and provenance checks |
| C02 | Recorded quotes, marks, trades, candles, funding and receipt order | Causal execution rechecks, marks, replay prefixes and regular equity |
| C03/C08 | Frozen feature/candidate evidence, family, direction, reference price and expiry | Exact protocol requests, duplicate suppression and opportunity inventory |
| C06 | Known settled funding and causal corrections, through C09 ledgers | Shared cash; unknown funding prevents new risk and keeps affected equity unknown |
| C07 | Fresh execution estimate at the proposed exact size, fee schedule and fill evidence | Size feasibility, actual entry risk, collateral reserve and tradability |
| C09 | Exit/holding policy, first entry opportunity and current-value outcome revisions | Conflict identity, holding-time ranking, positions, closes, partial reductions and fee/funding bookkeeping |
| C10 | Verified frozen models and compatible quantity-specific estimates | Lower-bound net expectancy eligibility and ranking; no size extrapolation |
| C11 | Pinned source/report hashes, complete scenario inventory, transitions and outcome revisions | Shared-capital replay uses existing production execution paths rather than a second exit engine |
| Injected account state | Cash, peak equity, positions, reservations, marks, coverage and source clocks | Every admission limit; no exchange account is queried |
| C12 | Frozen research model/source identity and predeclared counted portfolio recipe | Compatibility receipt after logged holdout access; full portfolio-policy inference remains separate |
| C14/C15, consumers | Allocation decisions, selected TradeIntents, risk snapshots, equity/ledger artifacts | Future persistent delivery, account reconciliation and forward comparison |

C01/C03/C07/C09/C10 do not import C13. C12 consumes C13 through an explicit compatibility method; C13 does not import or grant C12 promotion.

## Decisions and formulas

**One shared wallet.** Intraday and swing strategies use the same cash and capacity. One instrument may have one position/reservation; conflicting directions or strategy families do not receive hedge credit. Candidate identities remain seen after reservation expiry. Local expiry releases capacity; it does not establish a fill or cancel an exchange order.

**Predeclared tested quantities.** C10 estimates are tied to the quantity and execution protocol that generated their labels. Each ladder size therefore requires its own compatible estimate. C13 never multiplies a size-1 C11 outcome to invent a size-0.5 outcome, rounds to a new untested size, or substitutes a convenient alternate model. Each exact protocol has at most one frozen model. Live refinement, iterative sizing and within-window refits require new contracts and tests.

Let `s` be +1 for long and −1 for short, `q` remaining quantity, `m` fresh mark, `e` entry price, `z` stop, `f` closing taker fee rate, and `g = stop_gap_bps / 10000`. All economic arithmetic uses exact decimal operations in a fixed internal context; rational ranking comparisons avoid rounded-score ties.

| Measure | Formula/definition |
| --- | --- |
| Unrealized gross PnL | `s × q × (m − e)` |
| Wallet cash | Initial cash + each admitted C09 ledger's current keyed amounts; entry/exit fees paid once, funding revisions replace earlier amounts |
| Equity | Cash + unrealized gross; unknown if an open position lacks a fresh mark/risk assignment or funding is unknown |
| Spendable admission base | `min(cash, equity)`; unrealized gains cannot finance additional exposure |
| Existing stop-risk reserve | `q × [max(s × (m − z), 0) + max(m,z) × (g+f)]` |
| Proposed stop-risk reserve | `q × [s × (e − z) + max(e,m,z) × (g+f)] + entry_fee`; stop must lie on the loss side of the actual fill |
| Position collateral proxy | `q × max(e,m) + q × max(m,z) × f` |
| Proposal collateral proxy | `q × max(e,m) + entry_fee + q × max(e,m,z) × f` |
| Gross exposure | Sum of absolute mark notional; proposed entries reserve the larger of fill/mark notional |
| Absolute beta exposure | Sum of `abs(beta) × absolute notional`; opposing signs receive no offset |
| Joint shocks | All marks up, all marks down, and each position adverse independently, including a closing-fee reserve |
| Drawdown pause | Equity below the supplied/causally updated peak by more than the configured fraction pauses new admissions |

Risk is an admission reserve, not a guaranteed maximum loss. Gaps, stale execution and funding can exceed it. Stops and drawdown pauses do not create fictitious fills. Fraction caps apply to the current decision snapshot; subsequent market movement can breach them and suppress later entries.

**Ranking objective.** For each candidate/policy/horizon, the smallest eligible size anchors rank:

`score = lower_mean_net_R × [q × abs(actual_fill − stop)] / collateral_reserved / maximum_holding_hours`.

C09 defines R using actual entry-to-stop risk, so this conversion uses the same denominator. This is a frozen capital-time heuristic, not a prediction of realized holding time or an optimal allocation theorem. After ranking, try the largest eligible tested size that fits all remaining budgets, then smaller tested sizes. Tie ordering is deterministic from detection/candidate identity and canonical offer order. A selected candidate suppresses competing quantities and horizons. A higher score never overrides a failed limit, absent estimate or failed execution check.

**Concentration assumptions.** Default BTC/ETH assignments share one crypto group with beta magnitude 1. These are declared conservative assumptions with an availability timestamp and evidence string, not estimated historical correlations. Group stop risk and gross notional, absolute beta, total/per-trade risk, horizon risk, collateral, position slots and joint stress are all independently bounded. Unknown assets abstain until mapped. There is no default diversification credit, covariance optimizer, Kelly sizing or learned beta.

**Margin boundary.** Only `leverage: 1`, one-way, fully collateralized paper research is supported. Binance defines USDT notional as quantity times mark and has distinct order/position margin rules, including side and leverage effects. Our gross collateral reserve is deliberately a research proxy, not an implementation of those exchange formulas. [Binance margin requirements](https://www.binance.com/en-AE/support/faq/detail/4f83b65d83654b5e933f85ef12bf769d).

Binance uses mark price for unrealized PnL and liquidation and compares collateral with maintenance margin. Those mechanics require a separate tiered margin/liquidation model and historical evidence. C13 refuses leverage above 1; a breached full-collateral proxy makes the funded result unready and never generates an invented liquidation exit. [Binance liquidation protocols](https://www.binance.com/en/support/faq/detail/360033525271). Future authenticated account/bracket integration must be explicit; current bracket data cannot establish historical tiers. [Binance account APIs](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account).

Cross-asset volatility-management research motivates separately testing allocation rules; it does not validate this crypto policy or justify automatic adaptation. [Moreira and Muir, original paper](https://www.nber.org/papers/w22208).

## Causal funded replay

1. Verify each pinned C11 report and all its artifacts. Require the same recorded market dataset, complete prefix, metadata, fee/execution/funding settings and producer across sources. Recompute the actual C02 event-content prefix; store-local dataset IDs alone are insufficient identity.
2. Freeze all model publications before the decision window. Their training-source producer must match the tested C11 producer. Candidate features and exact protocols remain unchanged.
3. Replay available source events in `(available_ms, id)` order. At a timestamp finish the full source batch, then book already-admitted positions' causal closes/funding revisions, then evaluate new first-entry offers, then sample equity. Future final trade results never determine admission.
4. Consume each tested size's first executable C09 entry opportunity only. Recheck C07 on the current source prefix and require the same price, quantity, fee, source event and execution clock. A later same-instrument event within that timestamp suppresses the old opportunity. Do not wait for an untested better quote.
5. Admit only feasible offers; book only their real causal outcome states. A keyed funding correction revises shared cash rather than adding the old and new amounts. Remaining quantities follow the admitted C09 state, including partial exits.
6. Begin flat at explicit initial cash, retain a regular observation grid and declared outcome tail, and leave open positions open. Missing marks/funding keep affected equity unknown. Report total return, sampled dollar/fraction drawdown, regular arithmetic returns, source coverage and each exclusion. Annualized return/Sharpe remain null; these short synthetic grids cannot support them.

Sampling can miss between-grid drawdowns; a zero grid drawdown is not evidence of zero intratrade loss. No deposits, withdrawals, exchange margin offsets, joint order-book depletion, passive/partial entry or liquidation fills are simulated. One selected instrument at a time avoids reusing its quoted size for concurrent strategies; market impact across assets remains an assumption.

## Persistence, research and acceptance

Allocation is pure. A local C13 account can atomically reserve its proposals only with an unchanged expected snapshot hash. SQLite compare-and-swap, an append-only hash-linked journal and content-addressed batches prevent an interleaving writer from double-spending the same capacity. Identical retries return the same original batch. Reservations do not debit cash or become positions; explicit snapshot reconciliation is a caller responsibility. The account's source clock is retained so local writes cannot refresh stale account evidence.

A C12 experiment may predeclare `portfolio_recipe_hashes`, hashing the full C13 risk policy and replay configuration, including initial capital, grid and windows. Each recipe consumes a family trial slot. After logged final access, `research check-portfolio` checks exact recipe, source/report, model, window, runtime, complete funded outcomes and positive net against the frozen release. It retains an immutable compatibility receipt with `promotion_authorized: false` and `live_approved: false`.

That receipt is an engineering bridge. It does **not** run nested portfolio-policy search, validate a multi-release model bank, provide joint funded-return confidence bounds, or establish risk-adjusted outperformance. Those are required before portfolio promotion and are explicitly retained under C12-U06/C13-U04. Representative recorded markets, honest prior-trial disclosure, stress/capital/block sensitivity and prospective evidence remain necessary.

Acceptance for this increment: exact accounting and quantity compatibility, joint exposure limits, deterministic conflicts, fail-closed coverage, no future labels in admission, atomic recovery and local concurrency tests, production raw-input E2E, documented limitations and phased commits. Synthetic passing tests establish these engineering properties only.
