# Signal ledger and decision evidence

**Location:** Signals, `/signals`. **Access:** viewer. **Prerequisites:** a selected C14 session with at least one recorded cycle/candidate. Historical detector/backtest results alone do not create this prospective ledger.

## Investigate a candidate

1. Choose the workspace/session and current or recorded [knowledge cursor](HISTORICAL_REPLAY.md).
2. Use **All / Admitted / Rejected**, search by symbol/reason/ID, and load more rows as needed.
3. Open a row and inspect its original candidate, side, feature snapshot and conditional expectancy/cohort/uncertainty.
4. Inspect execution/cost/funding evidence, capital admission or rejection, paper path/fills/outcome and the delivery receipt separately.
5. Copy the complete hash or inspect full JSON when reproducing an observation. A shortened display hash is not a CLI input.

## Distinguish the states

- **Candidate:** a strategy setup was detected.
- **Admitted/rejected:** the finite paper account accepted it or recorded why it could not.
- **Paper lifecycle:** entry/open/closed, expiry, unfilled or unresolved evidence according to the frozen protocol.
- **Delivery state:** outbox/Telegram processing evidence; it does not mean a person acted on a message.

An admitted paper candidate need not have a sent message. A sent message need not mean a user read it or filled an order. Rejections/expiry are retained for coverage and diagnosis, rather than disappearing from the record.

The current C14 notices describe **evaluated paper fills** with `NO TRADE INSTRUCTION`; they are not actionable pre-entry instructions or real exchange positions.

## Local inspection

Replace the placeholders with the actual session/signal names. Custom store options must match the selected dashboard workspace:

```sh
conda activate tradee
python -m tradee signals status SESSION_NAME
python -m tradee signals list SESSION_NAME
python -m tradee signals signal SIGNAL_HASH
python -m tradee signals events SESSION_NAME
```

`status` can exit 2 when the runtime is unready; inspect its reasons. If the ledger is empty, confirm that a session has actually been created and ticked against captured evidence. Just opening the page, fitting a model or starting the worker does not generate candidates.

For exports, read [export scope](EXPORTS.md): the session CSV button exports latest session evidence, not the earlier replay cursor. For delivery controls, use [Telegram](TELEGRAM.md) and [operator jobs](OPERATOR_JOBS.md).
