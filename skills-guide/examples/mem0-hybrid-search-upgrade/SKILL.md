---
name: mem0-hybrid-search-upgrade
description: "Upgrade Mem0 OSS to hybrid BM25+semantic+reranking search."
---

# Mem0 Hybrid Search + Reranking Upgrade

## Context
Mem0 v2.0.x has built-in hybrid search (BM25 + semantic + entity boost) and reranking, but the dependencies aren't installed by default. This skill documents the full upgrade process on a self-hosted Hermes setup.

## Prerequisites
- Mem0 OSS with Qdrant backend (standalone binary at `~/.local/bin/qdrant`)
- Ollama for local embeddings (qwen3-embedding:4B) and LLM (glm-5)
- Hermes config at `~/.hermes/mem0.json` with `mode: "oss"`
- WSL2 with NVIDIA GPU (GTX 1060 6GB Pascal — CC 6.1)

## Steps

### 1. Install Dependencies

```bash
cd ~/.hermes/hermes-agent && source venv/bin/activate
pip install spacy fastembed sentence-transformers
python -m spacy download en_core_web_sm
```

- **spacy + en_core_web_sm**: Entity extraction (PROPER/TOPIC entities) + lemmatization for BM25
- **fastembed**: BM25 sparse text encoder (Qdrant/bm25 model, ~18MB)
- **sentence-transformers**: Cross-encoder reranker (BAAI/bge-reranker-base, 278M params)

### 2. Configure Reranker in mem0.json

Add to the `oss` block in `~/.hermes/mem0.json`:
```json
"reranker": {
  "provider": "sentence_transformer",
  "config": {
    "model": "BAAI/bge-reranker-base",
    "device": "cpu"
  }
}
```

Also add top-level `"rerank": true` to enable reranking by default.

**Note on device**: On GTX 1060, CPU is faster for the 278M param reranker (7.6ms vs 8.5ms per pair) — GPU data transfer overhead negates compute advantage for small models. Reserve GPU VRAM for the embedding model.

### 3. Patch Hermes _backend.py

File: `~/.hermes/hermes-agent/plugins/memory/mem0/_backend.py`

In `OSSBackend.__init__`, after the config dict is built:
```python
if "reranker" in oss_config:
    config["reranker"] = oss_config["reranker"]
```

In `OSSBackend.search`, pass rerank through:
```python
def search(self, query, *, filters, top_k=10, rerank=False):
    kwargs: dict[str, Any] = {"filters": filters, "top_k": top_k}
    if rerank:
        kwargs["rerank"] = True
    response = self._memory.search(query, **kwargs)
    return _unwrap_results(response)
```

### 4. Backfill BM25 Sparse Vectors

The Qdrant collection needs a `bm25` sparse vector slot. Backfill all existing points with BM25 sparse vectors.

**CRITICAL**: NEVER use `client.upsert()` to add sparse vectors — it replaces the entire point (dense vectors, payloads, everything). Use `client.set_payload()`.

If payloads are accidentally wiped, restore from `~/.mem0/history.db` (SQLite with ADD/UPDATE/DELETE events).

### 5. Force GPU Offload for Ollama Embedder

```bash
echo 'FROM qwen3-embedding:4B
PARAMETER num_gpu 34' > /tmp/gpu-modelfile
ollama create qwen3-embedding-gpu -f /tmp/gpu-modelfile
```

For 6GB GTX 1060 with 3.7GB VRAM budget:
- 36 layers total, 34 on GPU = 3.63GB actual VRAM
- 0.156s per embedding (2.6x faster than CPU)
- Update mem0.json embedder model to `qwen3-embedding-gpu`

### 6. Memory Consolidation Script

At `~/.hermes/scripts/memory_consolidation.py`. Scores: recency (30-day half-life) x 0.4 + importance x 0.4 + relevance x 0.2.

```bash
python ~/.hermes/scripts/memory_consolidation.py --dry-run  # preview
python ~/.hermes/scripts/memory_consolidation.py             # apply
```

### 7. CUDA 12.6 for WSL2 + Pascal

```bash
wget https://developer.download.nvidia.com/compute/cuda/12.6.1/local_installers/cuda-repo-wsl-ubuntu-12-6-local_12.6.1-1_amd64.deb
sudo dpkg -i cuda-repo-wsl-ubuntu-12-6-local_12.6.1-1_amd64.deb
sudo cp /var/cuda-repo-wsl-ubuntu-12-6-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update && sudo apt-get -y install cuda-toolkit-12-6
# ~/.bashrc:
export LD_LIBRARY_PATH=/usr/local/cuda-12.6/lib64:${LD_LIBRARY_PATH:-}
export PATH=/usr/local/cuda-12.6/bin:${PATH}
pip install torch --force-reinstall --index-url https://download.pytorch.org/whl/cu126
sudo systemctl restart ollama
```

## Verification

```python
from mem0 import Memory
m = Memory.from_config(config)
results = m.search("test query", filters={"user_id": "..."}, top_k=5, explain=True)
# bm25_score > 0 (was 0.000 before)
```

## Measured Improvements

| Metric | Before | After |
|---|---|---|
| Search score (CTF query) | 0.7828 | 0.8953 (+14%) |
| Search score (Experian query) | 0.6324 | 0.8164 (+29%) |
| Embedding speed | 0.413s | 0.156s (2.6x) |
| BM25 scores | 0.000 | 0.7-1.000 |
| Reranker | None | CPU 7.6ms/pair |

## Pitfalls

1. NEVER use `upsert` for sparse vectors — replaces entire point. Use `set_payload`.
2. Hash field must be string (pydantic rejects int). Use `str(hash(text))`.
3. Entity boosts start at 0 — entity store populates lazily on `add()`.
4. `ollama ps` shows "100% CPU" even with GPU — check `size_vram` in `/api/ps` JSON.
5. CUDA 13.0 drops Pascal (sm_61) — must use cu126.
6. nvidia-smi at `/usr/lib/wsl/lib/nvidia-smi` — add to PATH.
7. Reranker faster on CPU than GPU for 278M param models on GTX 1060.
8. nvidia-smi VRAM differs from Ollama reported VRAM on WSL2.