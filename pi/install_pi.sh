#!/bin/bash
# One-time setup on the Raspberry Pi (Raspberry Pi OS Bookworm or newer).
#   chmod +x install_pi.sh && ./install_pi.sh
set -e

echo "== Installing camera and OpenCV packages =="
sudo apt-get update
sudo apt-get install -y python3-picamera2 python3-opencv python3-numpy

echo "== Disabling Wi-Fi power saving (it drops the stream mid-flight) =="
sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf >/dev/null <<'EOF'
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager || true

chmod +x "$(dirname "$0")/start_sender.sh"

echo
echo "Done. Test the camera with:"
echo "  python3 $(cd "$(dirname "$0")" && pwd)/sender.py --host <LAPTOP_IP>"
