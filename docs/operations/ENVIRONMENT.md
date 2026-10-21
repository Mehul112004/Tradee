# Local environment and credentials

Tradee uses **one `.env` in the repository root**, shared by the Python CLI and backend services. There is no frontend credential file. The real file is ignored by Git; [`.env.example`](../../.env.example) contains blank placeholders suitable for a fresh checkout.

```sh
conda activate tradee
python -m pip install -e '.[live,dashboard]'
# On a fresh checkout only, then edit .env with your own values:
cp -n .env.example .env
chmod 600 .env
```

This checkout's local `.env` was created on 21 October 2026 with owner-only permissions and the two existing Telegram values copied from `../TBot/backend/.env`. They have been checked for format and equality locally; no real Telegram request was made as part of setup. Changes or rotations in TBot are not synchronized: edit Tradee's file separately and restart services that consume changed settings.

## Settings and reuse decisions

| Setting | Tradee consumer | Reuse from TBot |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | C14 explicit test/paper Telegram transport | Copied unchanged, including its name |
| `TELEGRAM_CHAT_ID` | Default destination for the standalone connectivity test | Copied unchanged; persistent sessions still require their own frozen IDs |
| `TRADEE_TELEGRAM_BOT_TOKEN` | Alternative token name, retained for existing Tradee commands | Optional; do not duplicate the token under both names |
| `TRADEE_WEB_OPERATOR_TOKEN` | Backend operator authentication | New Tradee setting, left blank for viewer mode; choose a separate random token when enabling operator requests |
| TBot `DATABASE_URL` | None; Tradee uses separate component SQLite stores | Not copied; it belongs to TBot's database |
| TBot `FLASK_APP`, `FLASK_ENV`, `SIGNAL_EXPIRY_CANDLES` | None; Tradee uses FastAPI and frozen strategy/runtime configurations | Not copied |
| TBot `GROQ_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_MAX_TOKENS`, `LLM_API_URL` | None; there is no implemented LLM consumer | Not copied |
| TBot `ANGELONE_API_KEY`, `ANGELONE_CLIENT_CODE`, `ANGELONE_PASSWORD`, `ANGELONE_TOTP_SECRET` | None; Tradee's provider is Binance public market data | Not copied |

No Binance API credential was present among those TBot settings. The Binance public endpoints currently used by Tradee require no API key/secret.

## Loading and precedence

The shared loader is `tradee/environment.py`, using [python-dotenv](https://pypi.org/project/python-dotenv/) pinned in the project dependencies and backend requirements. It resolves `.env` relative to the installed source checkout, independently of the working directory; it never searches parent directories or imports TBot settings automatically. CLI credential use and backend API/worker/runner settings share it. Direct engine/transport library callers still provide their own arguments.

For the token, precedence is exported `TRADEE_TELEGRAM_BOT_TOKEN`, exported `TELEGRAM_BOT_TOKEN`, file `TRADEE_TELEGRAM_BOT_TOKEN`, then file `TELEGRAM_BOT_TOKEN`. Other supported settings use exported value, then file value. An explicitly empty exported value disables its file fallback. The loader reads only supported application settings, never mutates `os.environ`, and does not evaluate shell commands or expand `${VARIABLE}` expressions. Do not `source` the file as a shell script.

Missing `.env` is allowed. Set **`PYTHON_DOTENV_DISABLED=1`** to disable file loading for isolated tests or deployments; exported credentials still work. C14/C15 automated verification subprocesses disable dotenv and remove both token names. The configured `.env` alone cannot opt into message sending or change a shadow session into paper mode.

The frontend receives no secrets through Vite. Never prefix credential names with `VITE_` or add them to frontend build configuration. The dashboard operator token can be entered through Settings for the current browser session, as described in [the runbook](../dashboard/DASHBOARD_RUNBOOK.md).

## Verification and research provenance

```sh
python -m unittest tests.test_environment tests.test_c14_cli tests.test_c14_telegram backend.tests.test_environment -v
```

These tests exercise precedence, redaction, cwd independence, literal parsing, missing/unreadable files, explicit Telegram send opt-in, mocked delivery and backend settings. They send no real messages. For one real delivery attempt, use [the Telegram smoke test](TELEGRAM.md).

Verified on 21 October 2026: all **847 Python tests** passed with `PYTHON_DOTENV_DISABLED=1 python -m unittest discover -v`, including backend and CLI E2E workflows. Focused configuration, Telegram and backend-settings checks passed too. Frontend formatting and production build passed. The local credential values were checked for equality with TBot and absence from tracked/staged source, and `.env` Git exclusion and mode `0600` were confirmed. No real Telegram message was sent.

Adding the loader changes the core's producer source hash. Existing frozen research artifacts retain their original identities; do not edit their stored hashes. A new compatible paper release must be generated and validated against the current source using the normal research/release workflow.
