#!/bin/bash
# Pixel 5に接続するスクリプト
# TailscaleのIPが変動するため、既知のIP全てを試す

KNOWN_IPS="100.78.130.66 100.74.138.17"
PORT=8022
USER=u0_a456
PASS=meronpan

for ip in $KNOWN_IPS; do
    echo "Trying $ip..."
    if ping -c 1 -W 2 "$ip" >/dev/null 2>&1; then
        if (echo >/dev/tcp/$ip/$PORT) 2>/dev/null; then
            echo "Connected: $ip:$PORT"
            sshpass -p "$PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p "$PORT" "$USER@$ip" "$@"
            exit $?
        else
            echo "$ip is up but port $PORT closed"
        fi
    else
        echo "$ip unreachable"
    fi
done

echo "All known IPs failed. Pixel 5 may have a new IP."
