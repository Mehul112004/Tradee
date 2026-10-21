# Telegram connectivity and paper notifications

There are **two separate tasks**: prove that a bot can deliver a simple message, or dispatch eligible notifications from a validated paper deployment. Neither is started automatically by opening the dashboard, starting a worker or adding `.env` credentials.

## One-message connectivity test

Prerequisites: root `.env` with `TELEGRAM_BOT_TOKEN` and numeric `TELEGRAM_CHAT_ID`; the bot must have access to the chat. In a private chat, open the bot and press Start if needed.

```sh
conda activate tradee
python -m tradee signals telegram-test --test-id manual_smoke_1 --send-paper
```

This makes one real `sendMessage` attempt containing **PAPER TEST**, **NO TRADE INSTRUCTION** and the test ID. It needs no database or strategy. The bot ID defaults to the token prefix and the destination defaults to `.env`; explicit `--bot-id` must match the token, and `--chat-id` can choose another numeric test destination.

Check JSON `ready: true`, `result.status: "sent"`, `reason: "telegram_accepted"` and a positive message ID; then verify the exact test ID in the chat. Messages are silent. On an ambiguous timeout, inspect the chat before another explicit attempt; no automatic retry occurs in this diagnostic.

## Strategy-path paper dispatch

Prerequisites: a current-source validated C14 deployment in **`paper_test`**, frozen numeric bot/chat, compatible token, running source capture, fresh evidence and a registered/observed C15 monitor. A successful connectivity test alone does not establish these.

For a deliberately CLI-owned session, this command opts into real paper notices:

```sh
python -m tradee signals watch SESSION_NAME --interval-seconds 1 \
  --max-cycles 3600 --send-paper
```

It processes eligible paper state/outbox with the frozen destination, freshness, expiry and admission checks. Keep the independent C15 monitor running as described in [Forward review](FORWARD_REVIEW.md). Do not run this as a second tick owner beside a dashboard-owned runner. Its notices describe evaluated paper fills, not pre-entry actionable instructions or actual user fills.

The dashboard and its owned runner expose **no Telegram-send operation**. A paper-test session without an explicit sender can still record paper outcomes/outbox evidence. `TELEGRAM_CHAT_ID` never changes an existing frozen session destination.

## Delivery failures and tests

Permanent rejection, safe retry/rate limiting and **ambiguous acceptance** are different outcomes. Persistent C14 dispatch has durable claims/recovery/reconciliation rules; do not delete outbox state or repeatedly resend an uncertain message. Read the reason and use evidence-backed reconciliation. Bot credentials are redacted, but destination IDs may appear in receipts.

```sh
python -m unittest tests.test_c14_telegram tests.test_c14_cli tests.test_environment -v
```

These tests use scripted transports and temporary files. They send **no** real messages. A synthetic demo's sent receipt is also scripted. Full setup and failure/reconciliation details: [Telegram operations](../../operations/TELEGRAM.md), [C14 operation](../../components/c14/C14_IMPLEMENTATION.md).
