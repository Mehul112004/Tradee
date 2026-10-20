# Telegram configuration and delivery test

Run these commands from the repository root with `conda activate tradee`.

## Credentials

Tradee's Telegram CLI reads the bot token from **`TRADEE_TELEGRAM_BOT_TOKEN`**. The numeric bot ID is the part of the token before `:`; the destination is a numeric Telegram chat ID. A username or phone number is not a chat ID.

The sibling TBot configuration is at `../TBot/backend/.env`, using **`TELEGRAM_BOT_TOKEN`** and **`TELEGRAM_CHAT_ID`**. Tradee does **not** load this file automatically or recognize `TELEGRAM_BOT_TOKEN` as an alias. Reusing that bot requires supplying its token under Tradee's variable name and choosing its chat ID explicitly. Do not commit the values, paste the token into a command argument, or publish the dotenv file.

The shipped C14 examples default to `shadow`, with no bot/chat configured. For a persistent paper deployment, freeze the numeric bot/chat in its `paper_test` session specification and supply the token to the runner process. The standalone test below needs no session or database. The dashboard has no Telegram-send endpoint.

## Send one real connectivity message

In the project's **zsh** terminal, securely enter the existing bot token and destination chat ID at the prompts. The token input is hidden and does not become a literal command in shell history:

```sh
conda activate tradee
read -s 'TRADEE_TELEGRAM_BOT_TOKEN?Telegram bot token: '
printf '\n'
export TRADEE_TELEGRAM_BOT_TOKEN
read 'TRADEE_TELEGRAM_CHAT_ID?Telegram chat ID: '
python -m tradee signals telegram-test \
  --bot-id "${TRADEE_TELEGRAM_BOT_TOKEN%%:*}" \
  --chat-id="$TRADEE_TELEGRAM_CHAT_ID" \
  --test-id manual_smoke_1 --send-paper
unset TRADEE_TELEGRAM_BOT_TOKEN TRADEE_TELEGRAM_CHAT_ID
```

The command makes **one real Telegram `sendMessage` attempt**. It sends a plain-text `Tradee PAPER TEST connectivity check` containing `NO TRADE INSTRUCTION` and your test ID. It does not run a strategy, create a database or send a trade signal. The bot must already have access to the chosen chat; for a private conversation, open the bot and press **Start** first.

Success is JSON with `ready: true`, `result.status: "sent"`, `result.reason: "telegram_accepted"` and a positive `message_id`. Then check the chat for `manual_smoke_1`: Telegram API acceptance alone does not prove that a person received/read it. The notification is silent, so do not rely on a sound or push alert. If the result is an ambiguous timeout, inspect the chat before deliberately rerunning; the command never retries automatically.

Tokens are never included in command output. Output does contain the numeric bot/chat IDs, so redact those if sharing logs.

## Run the offline regression tests

```sh
python -m unittest tests.test_c14_telegram tests.test_c14_cli -v
```

These tests use injected/mock transports and temporary local state. They check transport and CLI behavior **without delivering a real message**. Use the explicit smoke command above to verify credentials, connectivity and the actual destination.

See [C14 implementation](../components/c14/C14_IMPLEMENTATION.md) for session dispatch, outbox recovery and reconciliation rules, and [the documentation index](../index.md) for other components.
