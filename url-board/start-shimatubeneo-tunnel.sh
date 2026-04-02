#!/data/data/com.termux/files/usr/bin/bash
# Cloudflare quick tunnel for shimatubeNEO
# Auto-restart + Vercel url-board notification

LOCAL_PORT=8080
LOG=~/cloudflared-shimatubeneo.log
VERCEL_DIR=~/url-board
ENV_KEY=TUNNEL_URL_SHIMATUBENEO
ENV_KEY_UPDATED=TUNNEL_UPDATED_SHIMATUBENEO

update_vercel() {
    local tunnel_url="$1"
    echo "[$(date)] Updating Vercel: $tunnel_url"

    cd "$VERCEL_DIR" || return 1
    echo -n "$tunnel_url" | vercel env add "$ENV_KEY" production --force 2>&1
    echo -n "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | vercel env add "$ENV_KEY_UPDATED" production --force 2>&1
    vercel deploy --prod --yes 2>&1 | tail -1

    echo "[$(date)] Vercel updated"
}

# Make sure shimatubeNEO server is running
if ! pgrep -f "python.*shimatubeNEO/server.py" > /dev/null; then
    echo "[$(date)] Starting shimatubeNEO server..."
    cd ~/shimatubeNEO && nohup python server.py > ~/shimatubeneo.log 2>&1 &
    sleep 2
fi

while true; do
    echo "[$(date)] Starting cloudflared tunnel (port $LOCAL_PORT)..."

    cloudflared tunnel --url "http://127.0.0.1:${LOCAL_PORT}" > "$LOG" 2>&1 &
    CF_PID=$!

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
