#!/bin/bash
# Notify user when Hermes gateway comes online
# Runs in background — retries with backoff until Telegram API confirms delivery
BOT_TOKEN=$(grep -v '^#' /home/YOURUSER/.hermes/.env | grep TELEGRAM_BOT_TOKEN | head -1 | cut -d= -f2)
CHAT_ID="${TELEGRAM_ALERT_CHAT_ID}"
MESSAGE="♻️ Gateway online — Hermes is back and ready."

# Wait for gateway to connect to Telegram, then send notification
for i in 1 2 3 4 5 6; do
    sleep 10
    RESPONSE=$(curl -s --max-time 15 -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="$CHAT_ID" \
        -d text="$MESSAGE" 2>/dev/null)
    if echo "$RESPONSE" | grep -q '"ok":true'; then
        exit 0
    fi
done
exit 0