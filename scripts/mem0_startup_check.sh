#!/bin/bash
# mem0_startup_check.sh — health probe for the memory stack (Mem0 + Ollama + Qdrant).
# Watchdog semantics: SILENT when healthy, Telegram alert ONLY on failure.
# Wire as ExecStartPost on the gateway systemd unit, or run manually with --verbose.
# Sanitized for publication — paths use $HOME, credentials come from ~/.hermes/.env.
CHAT_ID="${TELEGRAM_ALERT_CHAT_ID:?set in .env}"
BOT_TOKEN=$(grep -v '^#' ${HOME}/.hermes/.env | grep TELEGRAM_BOT_TOKEN | head -1 | cut -d= -f2   # value only, token stays in env)
ENV_FILE="${HOME}/.hermes/.env"
VERBOSE=0
[ "$1" == "--verbose" ] && VERBOSE=1

ALERTS=()
OK=()

# ---------- 1. Ollama server alive ----------
if curl -s --max-time 10 http://localhost:11434/api/tags > /tmp/ollama_tags.json 2>/dev/null; then
    if python3 -c "import json; json.load(open('/tmp/ollama_tags.json'))" 2>/dev/null; then
        OK+=("ollama:alive")
    else
        ALERTS+=("ollama:alive-but-invalid-json")
    fi
else
    ALERTS+=("ollama:DOWN (no response on :11434)")
fi

# ---------- 2. Embedding model + GPU residency ----------
if [ ${#ALERTS[@]} -eq 0 ]; then
    # Embed probe (warm or cold — allow 60s for cold load)
    EMBED=$(curl -s --max-time 60 http://localhost:11434/api/embed \
        -d '{"model":"qwen3-embedding:4B","input":"startup probe"}' \
        -H "Content-Type: application/json")
    DIM=$(echo "$EMBED" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['embeddings'][0]))" 2>/dev/null)
    if [ "$DIM" == "2560" ]; then
        OK+=("embed:2560d")
    else
        ALERTS+=("embed:FAILED (dim=$DIM)")
    fi

    # GPU residency check — model should be in VRAM
    PS_JSON=$(curl -s --max-time 10 http://localhost:11434/api/ps)
    IN_VRAM=$(echo "$PS_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for m in d.get('models', []):
    if 'embedding' in m.get('name',''):
        vram = m.get('size_vram', 0)
        total = max(m.get('size', 1), 1)
        pct = 100 * vram // total
        print(pct)
        break
else:
    print(0)
" 2>/dev/null)
    if [ "${IN_VRAM:-0}" -ge 60 ]; then
        OK+=("gpu:embedding ${IN_VRAM}% in VRAM")
    else
        ALERTS+=("gpu:embedding only ${IN_VRAM:-0}% in VRAM (expect >60%) — likely running on CPU, check nvidia-smi")
    fi
fi

# ---------- 3. Qdrant collection green ----------
QDRANT=$(curl -s --max-time 10 http://localhost:6333/collections/hermes)
QSTATUS=$(echo "$QDRANT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('result',{}).get('status','?'))" 2>/dev/null)
QPOINTS=$(echo "$QDRANT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('result',{}).get('points_count','?'))" 2>/dev/null)
if [ "$QSTATUS" == "green" ]; then
    OK+=("qdrant:green (${QPOINTS} pts)")
else
    ALERTS+=("qdrant:${QSTATUS:-unreachable} (${QPOINTS} pts)")
fi

# ---------- 4. mem0 extractor LLM (the silent-killer probe) ----------
KEY=$(grep "^OLLAMA_API_KEY=" "$ENV_FILE" | cut -d= -f2   # value only, token stays in env)
MODEL=$(python3 -c "import json; print(json.load(open('${HOME}/.hermes/mem0.json')).get('oss',{}).get('llm',{}).get('config',{}).get('model',''))")
if [ -n "$MODEL" ] && [ -n "$KEY" ]; then
    RESP=$(curl -s --max-time 45 -X POST "https://ollama.com/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $KEY" \
        -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply OK\"}],\"stream\":false}")
    if echo "$RESP" | grep -q '"choices"'; then
        OK+=("extractor:$MODEL alive")
    else
        # double-check: maybe just slow
        sleep 2
        RESP2=$(echo "$RESP")
        if echo "$RESP2" | grep -q '"choices"'; then
            OK+=("extractor:$MODEL alive (slow)")
        else
            ERR=$(echo "$RESP2" | head -c 120)
            ALERTS+=("extractor:$MODEL FAILING ($ERR)")
        fi
    fi
else
    ALERTS+=("extractor:config missing (model='$MODEL', key=$([ -n "$KEY" ] && echo present || echo MISSING))")
fi

# ---------- Report ----------
send_telegram() {
    curl -s --max-time 15 -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="$CHAT_ID" \
        -d text="$1" > /dev/null
}

if [ ${#ALERTS[@]} -gt 0 ]; then
    MSG="🚨 Startup check FAILED — mem0/ollama issues detected:

$(printf '• %s\n' "${ALERTS[@]}")

Green items:
$(printf '• %s\n' "${OK[@]}" 2>/dev/null)

Investigate: check ollama.service, Qdrant container, and mem0.json extractor model."
    send_telegram "$MSG"
    echo "$MSG"
    exit 1
else
    if [ "$VERBOSE" == "1" ]; then
        MSG="✅ Startup check — all green:
$(printf '• %s\n' "${OK[@]}")"
        send_telegram "$MSG"
        echo "$MSG"
    else
        echo "startup check: all green ($(printf '%s ' "${OK[@]}"))"
    fi
    exit 0
fi