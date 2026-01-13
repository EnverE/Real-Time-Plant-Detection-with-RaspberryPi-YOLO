"""
Raspberry Pi Camera Streamer (Bookworm) - using rpicam-vid
"""

import subprocess
import sys

# === CONFIG ===
LAPTOP_IP = "192.168.137.1"  # Your Windows laptop IP
PORT = 8000
WIDTH = 640
HEIGHT = 480
FPS = 15          # Pi 3: keep ≤15 for smooth streaming
BITRATE = 2000000 # 2 Mbps (good balance)

# Use rpicam-vid (Bookworm's official tool)
cmd = (
    f"rpicam-vid -t 0 --width {WIDTH} --height {HEIGHT} "
    f"--framerate {FPS} --bitrate {BITRATE} --intra 5 --inline -o - | "
    f"ffmpeg -probesize 32M -analyzeduration 10M -i pipe: -f mpegts "
    f"udp://{LAPTOP_IP}:{PORT}"
)

print(f"📡 Streaming to udp://{LAPTOP_IP}:{PORT}")
print("Press Ctrl+C to stop.")

try:
    process = subprocess.Popen(cmd, shell=True)
    process.wait()
except KeyboardInterrupt:
    print("\n Stopping stream...")
    process.terminate()
    process.wait()
    print(" Done.")
