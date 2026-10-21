# Settings, access and data workspaces

**Location:** Settings, `/settings`, and top-bar workspace/session selectors. Viewer settings affect display/selection; operator authorization enables supported mutation requests. Neither edits a frozen strategy/model.

## Browser settings

- **Timezone:** formats table timestamps. Charts remain explicitly UTC; calculations/bar boundaries do not change.
- **Workspace:** selects a server-configured set of component database paths. A label marked synthetic is engineering evidence, not live account data.
- **Session:** selects an existing frozen deployment/cycle history. Selecting one does not start its runner.
- **Operator token:** the server's configured `TRADEE_WEB_OPERATOR_TOKEN`, held only in browser memory. Clear authorization or reload to remove it.
- **View context:** inspect the current workspace/session/cursor when diagnosing an unexpected result. Most selections are preserved in the URL; secrets are not.

## Default and custom workspaces

The default **Local recording** uses implemented component files under `data/`; the optional **Verification · synthetic** points to a retained engineering capture if it exists. Choosing an absent verification workspace does not generate its data. Use [the current-source demo](SYNTHETIC_DEMO.md) to create a new isolated learning workspace.

For a custom profile, create an ignored local configuration based on [the shipped example](../../../backend/profiles.example.json). From the root:

```sh
mkdir -p data
cp -n backend/profiles.example.json data/dashboard-profiles.json
```

Review/edit the file, then start the two services in **separate terminals**:

```sh
conda activate tradee
python -m backend.tradee_web --config data/dashboard-profiles.json
```

```sh
conda activate tradee
python -m backend.tradee_web.worker --config data/dashboard-profiles.json
```

`profiles[].root` locates each set of stores; `files` overrides specific component filenames; `state_path` owns the queue/runner records. Paths resolve from the process working directory, not the configuration file's folder, so use the repository root consistently or use reviewed absolute paths. Every domain store and web-state path must be distinct.

## Configuration ownership

The API/worker share this profile configuration. Direct core CLI/collector commands **do not** automatically inherit the browser's workspace or profile file: pass their matching `--db`, `--market-db`, etc. explicitly. Changing workspace does not relocate data or migrate a store.

The shared root `.env` supplies only supported application settings; it is not a database password file for SQLite and is not sent to Vite. Exported variables override file values, even when empty. Restart the API after changing its operator setting.

Current local origins are configured for ports 5173/8787. Merely choosing another frontend port can cause denied mutations; changing deployment origins is a deliberate backend configuration change. The current service is local, not a cloud/multi-user login system.

Related: [configuration catalog](../CONFIGURATION_REFERENCE.md), [operator jobs](OPERATOR_JOBS.md), [environment setup](../../operations/ENVIRONMENT.md).
