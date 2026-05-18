# Memory Architecture: Mem0 OSS + Qdrant

How persistent memory works in this deployment, and every failure mode we hit.

## The Three Legs

Memory extraction and retrieval is not one service — it's three independent network legs,
each with its own failure profile:

| Leg | Implementation | Latency (warm/cold) | Fails when |
|---|---|---|---|
| **Extractor LLM** | Ollama Cloud via OpenAI-compatible client | ~0.9s / — | API key invalid, model retired, quota |
| **Embedder** | Local Ollama serve, qwen3-embedding (2560-dim) | ~1.7s / ~25s | Ollama down, model unloaded |
| **Reranker** | Local cross-encoder (bge-reranker-base, CPU) | — / ~47s cold | Model missing from disk |

The critical property: **the embedder leg has no timeout by default** (Ollama client passes
none). If Ollama dies, memory writes hang *indefinitely* — the agent doesn't error, it
silently stalls. Configure timeouts explicitly; do not trust library defaults.

## Retrieval Pipeline

```
user message
    │
    ▼
[semantic search] ── Qdrant cosine over 2560-d embeddings
    │                  + BM25 sparse leg
    ▼
[candidate set]
    │
    ▼
[cross-encoder rerank] ── bge-reranker-base scores query×memory pairs
    │
    ▼
[temporal boost] ── recent memories scaled up:
    │                 weight 0.2, half-life ~1 week (604800s)
    ▼
[final ranking → injected into context]
```

**Why hybrid (semantic + BM25)?** Pure vector search misses exact identifiers — account
numbers, file paths, exact API names. BM25 catches those. The two legs disagree in
complementary ways, and the reranker arbitrates.

**Why temporal boost?** A long-lived agent accumulates stale facts ("currently working on X")
that outrank current reality. A 0.2-weight recency boost keeps "what's true now" visible
without erasing durable knowledge.

## Extraction Gotchas

1. **The 401-from-nowhere bug:** mem0 OSS instantiates an OpenAI client for the LLM leg
   *regardless of provider config*. Without `OPENAI_API_KEY` in the environment, the
   constructor throws before your real key is ever used. Fix: export a dummy
   `OPENAI_API_KEY`, point `openai_base_url` at your actual endpoint.

2. **Retired models fail silent:** if your cloud provider quietly retires a model version
   (HTTP 410 on every call), extraction dies but nothing else does. Symptom: memory count
   flatlines. The health check below probes the *extractor*, not the search API — searching
   can work while extraction is dead.

3. **Search API drift:** mem0's `search()` requires `filters={"user_id": ...}` in recent
   versions — without the filter it returns nothing and raises no error. If search suddenly
   returns empty, check the filter first.

## Health Checking (Watchdog Semantics)

The startup check (see `scripts/mem0_startup_check.sh`) probes all three legs on gateway
boot, wired via systemd `ExecStartPost`:

- **All green → exit silently.** A monitor that reports success trains you to ignore it.
- **Any failure → Telegram alert with specifics** (which leg, what error)

Probing strategy, in order of cheapness:
1. Ollama `/api/tags` alive (JSON parses)
2. Embedder model responds to a single embed call
3. Qdrant HTTP green (`/readyz`)
4. Extractor LLM round-trip (the leg most likely to break silently — probe it *first* if
   you can only afford one)

## Consolidation

Memory accumulates forever without pruning. The consolidation script
(`scripts/memory_consolidation.py`, weekly cron) scores each memory:

```
score = 0.4 × recency (exponential decay, 30-day half-life)
      + 0.4 × importance (category defaults + keyword boost)
      + 0.2 × relevance (access-count sigmoid)
```

- Below `prune_threshold` (0.15) → **soft-expired** (Qdrant payload flag, still recoverable)
- Stale keyword patterns (finished events, past deadlines) → hard-expired
- Identity/employment/preference memories → **never pruned** (keyword-protected)

Soft expiry over deletion is deliberate: a wrong prune decision is reversible for a week,
which is how long it takes to notice a missing memory in practice.