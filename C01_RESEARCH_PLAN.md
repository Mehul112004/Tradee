# C01 — Instrument and universe registry

Discussion draft — 13 September 2026. Updated 14 September 2026: **C01 first version implemented after the user's explicit instruction to initialize the repository and start building with Binance**. Operational instructions are in [README.md](/Users/artemis/Mehul/Tradee/README.md).

## First-version implementation decisions

- Binance public exchangeInfo is the provider. Preserve all returned contracts for audit and restrict eligible membership using explicit crypto/perpetual/USDT quote-and-margin checks.
- Default enabled universe: BTCUSDT and ETHUSDT, configurable through the CLI/Python policy. Unicode exchange symbols are supported.
- Python 3.11+ standard-library domain module and CLI, SQLite schema v1, atomic refreshes and consistent as-of reads. This isolated metadata store does not mandate SQLite for later components.
- Immutable application-level observations, semantic rule versions and saved policy/universe snapshots. No inferred historical effective dates; missing/uncertain/stale records are not eligible for new signals.
- Startup plus 15-minute polling when the watcher is explicitly run; 30-minute freshness cutoff. No background daemon is installed automatically.
- Missing symbols remain in the catalog and are unknown until observed again. Ambiguous identity changes remain quarantined for a future reviewed reconciliation workflow.
- The automated suite and public-provider integration verify this scope. Historical metadata reconstruction, HTTP service/dashboard, liquidity-based selection and identity reconciliation remain deferred.

## Purpose

C01 answers: which instrument does a record refer to, what contract rules do we know, and is that instrument eligible for the requested use at the requested time? It supplies trustworthy scope and constraints; it does not predict profitable setups.

## Proposed first version

Discover and preserve metadata for Binance crypto USDT-margined perpetual contracts. Maintain a separate, configurable enabled universe, initially proposed as BTCUSDT and ETHUSDT. Discovering a contract does not automatically enable candle downloads, strategy scans or Telegram alerts.

Restrict the product explicitly using contract/product metadata, quote asset and margin asset; a symbol ending in USDT alone is insufficient. Preserve raw metadata so unsupported or newly introduced classifications can be investigated. Unknown classifications must not silently enter the enabled universe.

## Internal parts

| Part | Responsibility | Proposed output |
| --- | --- | --- |
| Metadata adapter | Fetch current exchange metadata; timeout/retry/error handling; preserve the response and receipt time | Raw metadata snapshot |
| Instrument catalog | Normalize contract identity, assets and lifecycle metadata; retain old entries | InstrumentSpec |
| Rule registry | Preserve filters by type, exact decimal increments, quantity/notional constraints and supported order capabilities | RuleSetVersion |
| Observation history | Append immutable observations, detect semantic changes, record provenance and evidence coverage | MetadataObservation and version history |
| Universe policy | Apply product scope, configured allowlist and observed eligibility; record rejection reasons | UniverseSnapshot |
| Query and health interface | Current/as-of lookup, freshness status, exclusions and unavailable-history explanations | EligibilityDecision and coverage report |

Binance's exchange-information endpoint describes assets, contract type/status, onboarding date and filters. Its documentation explicitly distinguishes precision fields from actual tick/step increments. Use filter values rather than deriving trading increments from display precision. [Official reference, checked 13 September 2026](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).

## Identity and contracts

Use a stable internal instrument ID with explicit venue and product fields. Keep exchange symbol and alias history separate; do not silently join a renamed or relisted contract to a previous one. A first version can quarantine ambiguous identity changes for review.

Proposed records:

- InstrumentSpec: ID, venue/product, exchange symbol, base/quote/margin assets, reported contract classification, source-reported lifecycle facts and provenance.
- RuleSetVersion: typed filters and capabilities, raw original values, parsed exact decimals, observation reference and evidence timestamps.
- UniverseSnapshot: policy version, decision time, members and excluded candidates with reasons, metadata versions, source freshness, and historical evidence limitations.
- EligibilityDecision: requested use/time, eligible/ineligible/unknown, applicable evidence and reasons.

Record observed time separately from source-reported effective time, which may be unknown. Never set an exact historical rule-change time merely because polling first noticed the change then. Unchanged successful refreshes advance freshness without inventing a new semantic rule version.

## Historical and operational behavior

- Today's metadata is not proof of last year's rules or uninterrupted trading status. A reported onboarding date does not establish complete historical availability.
- For periods before trustworthy observations, report unknown rules/status. C12 may permit an explicitly labelled research assumption; C01 must not silently treat it as verified history.
- As-of queries distinguish facts observed by that time from historical facts established later. Research manifests specify which evidence policy they allow.
- Preserve old snapshots and disappeared contracts. An absent symbol may indicate removal or incomplete retrieval; do not infer a precise delisting time from one missing observation.
- Failed refreshes do not erase the catalog or falsely refresh its age. Retain last-known records and expose their age; stale or uncertain eligibility prevents new live signals under a declared threshold.
- Existing paper positions still need monitoring when new-entry eligibility is lost. C01 reports status; the shared trade policy decides position handling.
- Proposed schedule for discussion: refresh on startup and every 15 minutes; block new live eligibility after 30 minutes without a successful verified refresh. These are configurable design proposals, not exchange requirements, and polling leaves an observation gap.

## Dependencies and consumers

C01 starts from exchange metadata and configuration; it has no required dependency on another Tradee component. Later liquidity-based selection can consume a completed C02 snapshot without creating a startup cycle.

| Consumer | What it receives and why |
| --- | --- |
| C02 | Instrument IDs and separately configured collection scope; prevents product mixing |
| C07 | Trading rules for execution feasibility; account-specific fees remain C07's responsibility |
| C08 | Enabled instruments for candidate detection |
| C09 | Contract/rule identity for trade-intent validation |
| C11 | Historical membership and rule evidence/assumptions |
| C12 | Frozen universe/version references and evidence coverage |
| C13 | Instrument constraints for portfolio sizing |
| C14 | Current eligibility, freshness and suppression reasons |

C01 owns the metadata adapter. C02 owns candle/trade/quote ingestion. C01 defines constraints; C07/C09 apply order-type and side-specific execution policies. C13 owns capital/risk limits. C06 owns funding calculations. Current exchange information is not a substitute for an account-specific margin/leverage model.

## Verification before calling C01 complete

1. Correctly distinguish supported contracts from spot, delivery, other margin assets and unsupported classifications using fixtures.
2. Keep discovery separate from enabled membership; allowlist changes create reproducible policy snapshots.
3. Preserve typed filters and decimal increments; distinguish missing, unsupported and valid values.
4. Record a rule/status change without overwriting history; unchanged refreshes update freshness correctly.
5. Return unknown for unsupported historical periods; never backdate first observation as a verified effective time.
6. Handle failed, malformed and incomplete refreshes without clearing or falsely validating the catalog.
7. Recover persisted state after restart and reproduce a frozen universe snapshot.

Fixtures provide deterministic verification. The test suite covers the cases above, and the implemented provider has successfully fetched and normalized the live Binance catalog. Captured fixture values are observations, not permanent exchange rules.

## Original discussion questions and selected defaults

1. **Universe:** discover the supported catalog and initially enable BTC/ETH, enable another explicit list, or aim for all eligible contracts from the first release?
2. **Historical evidence:** accept labelled unknown/assumed metadata in exploratory research while reserving verified claims for covered periods? Strict historical execution validation cannot proceed without adequate rule evidence.
3. **Refresh/freshness:** accept the proposed polling policy or choose another operational requirement?
4. **Interface/storage:** proposed first delivery is a Python domain module, persistent versioned metadata, and a small CLI/API query surface; choose database and concrete schema in the finalized implementation plan. A dashboard is not required to prove C01 works.

The explicit implementation request superseded the earlier discussion-only status. The first-version decisions above resolve defaults for this increment; larger changes to scope remain future component work.
