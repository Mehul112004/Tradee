# Shutdown, backup and recovery

SQLite is a file database, but copying only a live `.sqlite3` file can omit committed WAL state. Treat component stores, profile configuration and the web queue as related evidence with independently owned writers.

## Planned shutdown

1. In Operations, request **stop runner** for owned paper runners and confirm the stopped state. An owned runner may outlive API/worker; closing a browser is not a stop request.
2. Finish/inspect running jobs and cancel queued work you do not want. Running core publications should reach their atomic boundary; do not kill a write merely because the page is slow.
3. Stop a separately CLI-owned C14/C15 watch loop in its terminal with Ctrl+C. Keep one tick owner per session.
4. Stop the Binance collector and metadata watcher in their own terminals with Ctrl+C.
5. Stop worker, Vite (if used) and API with Ctrl+C. The next startup does not automatically restart collectors, runners or Telegram dispatch.

Do not delete lock files to take over a live process. Investigate stale ownership and use the explicit runner recovery flow when the process lock is actually free.

## What to back up

Include every configured component store, the separate web-state store, profile JSON, frozen scenario/policy/calendar files and any required raw inputs/manifests needed for reproduction. The root `.env` is a separate private credential backup concern: it is ignored by Git and is not included in source commits. Protect it separately and never publish it with a report bundle.

For running stores use SQLite's supported backup API. For straightforward filesystem copying, first stop **all writers** to those stores. Preserve the original set; do not independently merge advanced copies or restore over an active recording. Existing hashes detect some corruption/substitution but do not authenticate data against a hostile editor.

## Restore for inspection first

1. Restore into a **new directory** and retain the original recovery copy.
2. Create a reviewed profile pointing to the restored component files and a deliberately chosen separate/restored web-state path.
3. Start the API in viewer mode. To force this one process to ignore a nonblank file token, use an empty exported override:

```sh
conda activate tradee
TRADEE_WEB_OPERATOR_TOKEN= python -m backend.tradee_web \
  --config data/restored-profiles.json
```

4. Verify source/schema/artifact integrity, session revisions, cash/positions and journals. A restore can contain old queued requests and stale runner reservations.
5. Keep the worker stopped until those queued/interrupted requests are reviewed. Starting a worker against a restored queue can execute its pending requests. Decide explicitly whether to reuse or create fresh web state.
6. Review producer/Python compatibility before resuming operational processing. Old research remains historical evidence; a new source version may require new research/deployment rather than replaying old operational state.

`data/restored-profiles.json` above is a placeholder for a profile you create/review, not a shipped recovery file. See [settings/workspaces](SETTINGS_AND_WORKSPACES.md) for path semantics. Production disk-failure, unattended recovery and large real-feed restore drills remain [operational validation work](../../platform/COMPONENT_UPGRADES.md); unit tests are not proof those drills have occurred.
