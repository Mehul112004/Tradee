# Synthetic demo workspace

Use this to learn the interface with populated data, without collecting Binance data or sending real Telegram messages. It generates a **current-source** C01–C15 engineering workflow with artificial prices, reduced research thresholds and scripted delivery. Its performance is not a strategy result.

## Generate and open

Prerequisites: [install dependencies](../START_HERE.md), then choose an output directory that does **not** already contain a demo. The workflow can take several minutes.

```sh
conda activate tradee
python -m scripts.verify_c15 --output data/user-guide/demo1
```

After successful completion, create `data/user-guide/profiles.json` containing:

```json
{
  "default_profile": "demo",
  "state_path": "data/user-guide/web.sqlite3",
  "profiles": [
    {
      "id": "demo",
      "label": "Learning demo - synthetic",
      "root": "data/user-guide/demo1/research",
      "synthetic": true,
      "files": {
        "c14": "../c14.sqlite3",
        "c15": "../c15.sqlite3"
      }
    }
  ]
}
```

Start the API with this configuration, replacing any existing API on port 8787:

```sh
python -m backend.tradee_web --config data/user-guide/profiles.json
```

Use the [development or built frontend](../START_HERE.md#2-choose-how-to-open-the-dashboard). No worker is needed to inspect the completed demo. If you later use dashboard jobs, start its worker with the same `--config data/user-guide/profiles.json`.

## First walkthrough

1. Select **Learning demo - synthetic** and session **paper_demo**.
2. Open **Overview**, then **Signals**. Inspect one admitted candidate and one capital rejection.
3. Open **Portfolio** and compare the shared wallet with independent candidate outcomes in **Research**.
4. Open **Forward review**, choose monitor **forward**, and compare report vintages.
5. Use the recorded cursor in **Signals** to inspect an earlier cycle before an outcome matured. Return to the current view afterward.
6. Open **Data quality** to inspect pinned datasets. Markets can show recorded artificial candles; additional materialization may be needed for feature overlays.

Expected result: stored evidence and paper lifecycle/review receipts are visible. A scripted `sent` receipt is not real Telegram delivery. This historical demo is for inspection; do not try to start its already-ended paper session as a new live session.

If the script rejects an existing directory, choose `demo2` and update both profile roots accordingly; do not erase an existing evidence directory to make a rerun pass. If the dashboard remains empty, verify the custom `--config`, selected workspace and successful script completion.

Related: [overview](OVERVIEW.md), [testing](TESTING_AND_TROUBLESHOOTING.md), [C15 engineering verification](../../components/c15/C15_VERIFICATION.md).
