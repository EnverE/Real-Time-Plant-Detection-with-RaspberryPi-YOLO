#!/bin/bash
# Auto-restart wrapper for sender.py.
# The GUI launches this over SSH; it also works standalone:
#   ./start_sender.sh --host 192.168.137.1
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while true; do
    echo "[WRAP] Starting sender at $(date)"
    python3 "$DIR/sender.py" "$@"
    echo "[WRAP] Sender exited. Restarting in 3s..."
    sleep 3
done
