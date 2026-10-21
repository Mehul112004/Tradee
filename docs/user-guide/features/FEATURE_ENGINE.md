# Feature engine and indicators

**Location:** Markets → C03 overlays/evidence; Operations → Research & data jobs → features. **Access:** viewer for existing results; operator plus worker for UI materialization. **Prerequisites:** a pinned C02 dataset and enough earlier finalized bars for warm-up.

C03 computes causal, versioned features from recorded evidence. The catalog includes returns, EMA/ATR/RSI, volatility, normalized trend/price distances, volume/VWAP, imbalance and quote context. The exact catalog/formulas are inspectable; not every chart timeframe/name is included in every preset.

## Discover and materialize

```sh
conda activate tradee
python -m tradee features list
python -m tradee features explain rsi14
python -m tradee features run DATASET_HASH --config configs/c03_baseline.json
```

Replace `DATASET_HASH` with an actual snapshot from your stores. Copy the returned run identity and inspect it:

```sh
python -m tradee features summary RUN_HASH
python -m tradee features manifest RUN_HASH
```

For the dashboard job, select **features**, review its actual `dataset_hash` and `config`, then submit and inspect Job history. A minimal requested set such as `ema20`, `ema50`, `atr14`, `rsi14` can differ from the larger baseline; retain the chosen definition in its manifest.

## Configuration and interpretation

[c03_baseline.json](../../../configs/c03_baseline.json) declares feature names, timeframes, stability policy, seed tolerance, quote freshness, candle grace and processing delay. Global `--db` goes before `features`; `--market-db` and `--feature-db` go before `run` for custom stores.

Each value has validity/stability and lineage. Warm-up is not interchangeable with “the value is non-null.” Long-seeded indicators may need more history than their nominal period. Missing/gapped/provisional or future-unavailable inputs can suppress outputs. Do not fill them with zeroes to force downstream admission.

Changing the output range does not create preceding warm-up bars. Capture earlier history and pin a suitable dataset, then regenerate the materialization. Changing a feature formula/config changes its frozen identity.

C08/C11 can compute their required production features internally; a manual C03 materialization is useful for reusable inspection/charts and is not a substitute for those stages' own compatible feature snapshots.

Related: [Markets](MARKETS_AND_CHARTS.md), [strategy candidates](STRATEGY_CANDIDATES.md), [formula specification](../../components/c03/C03_FEATURE_SPEC.md), [C03 operation/validation](../../components/c03/C03_VERIFICATION.md).
