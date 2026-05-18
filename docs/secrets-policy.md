# Secrets & Privacy Policy

What never enters this repository, and the mechanisms that keep it that way.

## Never Committed

| Category | Examples | Mechanism |
|---|---|---|
| Credentials | API keys, bot tokens, passwords | `.env` gitignored; `.example` templates only |
| Identifiers | Telegram chat/user IDs, phone numbers | `[REDACTED]` / env vars in all committed docs |
| Real memory data | Conversation-derived facts | Synthetic samples in `samples/` only |
| Client data | Anything from professional engagements | Not referenced at all |
| Infrastructure specifics | Real hostnames, internal paths | Generic `$HOME/.hermes` paths |

## Why `.example` Files

Every config template in `examples/` ends in `.example`. The workflow:

```
cp config.yaml.example config.yaml   # then fill in secrets
git status                            # config.yaml ignored, .example tracked
```

The `.example` file carries the *structure and commentary*; the real file carries the
secrets. The two never touch.

## Pre-Publication Checklist

Run before every push:

- [ ] `grep -rE '(sk-[A-Za-z0-9]{20,}|ghp_|bot[0-9]{9}:)' .` → no hits
- [ ] `grep -rn 'TELEGRAM_BOT_TOKEN=' --include='*.sh'` → values come from env only
- [ ] No hardcoded chat/user IDs (search for 9-10 digit numbers)
- [ ] `git log -p --all | grep -iE 'api_key|token'` → only placeholders in history
- [ ] Memory samples are synthetic (`sample_user`, fabricated facts)

## If a Secret Leaks Anyway

1. **Rotate first, clean second** — a leaked key is live until revoked; history rewriting
   doesn't un-leak it
2. Revoke at the provider (Ollama Cloud / BotFather / etc.)
3. Then rewrite history (BFG / filter-repo) or just treat the rotated secret as burned
   and move on — for a personal deployment, rotation is usually sufficient