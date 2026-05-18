# Synthetic Memory Samples

**These are fabricated examples for format documentation. Real memory data is never
committed** — it contains conversation history, personal facts, and identifiers.

## Sample memory (Mem0 format)

What the extractor produces from a conversation turn:

```json
{
  "id": "m_9f2c1a7b",
  "memory": "User prefers technical documents as PDF rather than plain text, and wants measurements in metric units.",
  "user_id": "sample_user",
  "metadata": {
    "category": "preference",
    "source": "telegram",
    "timestamp": "2026-08-15T14:32:11+08:00"
  }
}
```

## What good extracted memories look like

| Good | Bad (why) |
|---|---|
| "User's sister's birthday is in March" | Specific, stable, identity-class |
| "User is currently job hunting" | Temporal — will need expiry when it ends |
| "User hates being asked twice for the same file" | Behavioral preference, actionable |
| "User said hi at 14:02" | Noise — extraction should never store chitchat |
| "User might possibly like maybe tea" | Hedged — extractor should commit or drop |

## Consolidation scoring in practice

Given the sample memories above after 90 days of no access:

```
recency(90d)  = 0.5^(90/30)      = 0.125  → ×0.4 = 0.050
importance    = preference=0.6     keyword boost: "hates being asked twice" → 0.8 → ×0.4 = 0.320
relevance     = access_count 0     sigmoid(0) = 0.5 → ×0.2 = 0.100
─────────────────────────────────────────────────
score                                          = 0.470  → survives threshold 0.15
```

The job-hunting memory, once the user stops mentioning it: recency decays, no identity
keyword protection, access_count flat → it drops below threshold in ~6 weeks and gets
soft-expired. That's the system working as designed — stale facts retire themselves.