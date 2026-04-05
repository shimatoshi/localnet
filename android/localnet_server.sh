#!/data/data/com.termux/files/usr/bin/bash
cd ~/localnet
while true; do
    python3 server.py >> ~/server.log 2>&1
    echo "server exited, restarting in 3s..." >> ~/server.log
    sleep 3
done
