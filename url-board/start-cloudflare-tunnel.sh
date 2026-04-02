#!/data/data/com.termux/files/usr/bin/bash
# Cloudflare quick tunnel for localnet
# - starts cloudflared, extracts URL
# - updates Vercel url-board via CLI
# - auto-restarts on crash

LOCAL_PORT=8789
LOG=~/cloudflared.log
VERCEL_DIR=~/url-board

update_vercel() {
    local tunnel_url="$1"
    echo "[$(date)] Updating Vercel: $tunnel_url"

    cd "$VERCEL_DIR" || return 1
    echo -n "$tunnel_url" | vercel env add TUNNEL_URL production --force 2>&1
    echo -n "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | vercel env add TUNNEL_UPDATED production --force 2>&1
    vercel deploy --prod --yes 2>&1 | tail -1

    echo "[$(date)] Vercel updated"
}

while true; do
    echo "[$(date)] Starting cloudflared tunnel (port $LOCAL_PORT)..."

    cloudflared tunnel --url "http://127.0.0.1:${LOCAL_PORT}" > "$LOG" 2>&1 &
    CF_PID=$!

    # Wait for URL
    TUNNEL_URL=""
    for i in $(seq 1 15); do
        sleep 2
        TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)
        if [ -n "$TUNNEL_URL" ]; then
            break
        fi
    done

    if [ -n "$TUNNEL_URL" ]; then
        echo "[$(date)] Tunnel active: $TUNNEL_URL"
        update_vercel "$TUNNEL_URL"
    else
        echo "[$(date)] Failed to get tunnel URL, killing cloudflared"
        kill $CF_PID 2>/dev/null
        sleep 5
        continue
    fi

    wait $CF_PID
    echo "[$(date)] Tunnel stopped (exit=$?). Restarting in 10s..."
    sleep 10
done
