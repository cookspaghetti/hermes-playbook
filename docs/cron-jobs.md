# Scheduled Jobs: Cron Without the LLM Tax

How recurring autonomous work is scheduled, and the `no_agent` pattern that makes it cheap
and reliable.

## The Two Modes

Hermes cron jobs can run in two modes. Choosing correctly is the single biggest
reliability lever:

| Mode | How it runs | Use when |
|---|---|---|
| **Agent mode** | Scheduler spawns a fresh agent session; LLM reads prompt, uses tools | Output requires judgment: summarizing a feed, drafting a report from changing inputs |
| **`no_agent` mode** | Scheduler runs `script` directly; stdout is delivered verbatim (or saved) | Output is deterministic: metrics, watchdogs, data pulls, reminders |

**Rules of thumb:**

1. If a human could predict the output exactly (a fixed sentinel message), use `no_agent`.
2. `no_agent` jobs cost zero tokens, never hallucinate, never drift from the spec, and fail
   with real error codes instead of plausible-looking text.
3. The failure mode of agent-mode recurring jobs is *slow corruption*: each run drifts
   slightly from intent; by run 15 the job is doing something adjacent to what you asked.
   Scripts can't drift.
4. If you need LLM judgment, wrap it in a script anyway — the script calls the LLM
   explicitly and validates the output. Keep the scheduler dumb.

## Job Definition

Jobs live in `~/.hermes/cron/jobs.json`. A representative `no_agent` job:

```json
{
  "id": "a66f04f3a7f0",
  "name": "Memory Consolidation",
  "prompt": "",
  "script": "memory_consolidation.py",
  "no_agent": true,
  "schedule": { "kind": "cron", "expr": "0 3 * * 0" },
  "enabled": true,
  "deliver": "origin",
  "origin": { "platform": "telegram", "chat_id": "[REDACTED]" }
}
```

## Delivery Semantics (learned the hard way)

- **Watchdog jobs must stay silent when healthy.** A daily "everything OK" message is
  training the user to swipe notifications away. Silence = healthy; only failure speaks.
- **Delivery targets:** `origin` (the chat that created the job), a specific
  `platform:chat_id`, or `local` (save to disk, no message). Watchdogs → alert chat only
  on failure. Reports → `origin`. Telemetry nobody reads → `local`.
- **Empty stdout in `no_agent` mode = silence.** This is a feature: build your script so
  "nothing to report" produces zero bytes, and the job goes dark exactly when there's
  nothing to say.
- **Non-zero exit / timeout = error alert.** The scheduler converts failures into
  notifications, so a broken watchdog can't fail silently either.

## Job Hygiene

- **One job = one concern.** Don't write a mega-script that pulls metrics AND alerts AND
  posts; you'll want different schedules for those within a month.
- **Idempotency:** cron can double-fire after sleeps/hibernate. Scripts should tolerate
  running twice.
- **State files** (`~/.hermes/scripts/state/*.json`) over re-deriving facts; last-run
  timestamps, dedup keys, seen-IDs. Cheap and debuggable.
- **Never embed secrets in job definitions.** Jobs read the `.env` file like everything else.

## Worked Examples From This Deployment

| Job | Schedule | Mode | Output shape |
|---|---|---|---|
| Memory consolidation | Sun 03:00 | `no_agent` | silent on success, summary of expired memories to `local` |
| Daily library sweep | 09:00 daily | `no_agent` | short status line to home channel |

A recurring job's success message should be *deliberately* terse. The value is in the failure
case: if the scheduled message is anything other than the known-good sentinel, the user knows
the pipeline broke — and the message contains the actual error, not an LLM's summary of it.