# Troubleshooting

Work top-down: network first, then SSH, then the stream.

## Quick health check

```cmd
netsh wlan show hostednetwork      :: Status should say "Started", clients 1
ping 192.168.137.100               :: the Pi should reply
ipconfig                           :: the laptop should have 192.168.137.1
```

```bash
python tools/deploy_pi.py          # proves SSH works and refreshes the sender
```

---

## Hosted network won't start

### `The wireless LAN interface is powered down`

The Wi-Fi radio is off. In an Administrator command prompt:

```cmd
netsh interface set interface "Wi-Fi 2" admin=enable
net stop wlansvc
net start wlansvc
netsh wlan start hostednetwork
```

Also check that airplane mode is off.

### `The hosted network couldn't be started`

The adapter may not support hosted networks:

```cmd
netsh wlan show drivers
```

Look for `Hosted network supported : Yes`. Many modern built-in adapters say No, which
is what the external USB Wi-Fi adapter is for. Plug it in, then re-run
`scripts/start_hotspot.bat` as administrator.

### Laptop shows `169.254.x.x` instead of `192.168.137.1`

Internet Connection Sharing didn't attach:

```cmd
net stop SharedAccess
net start SharedAccess
netsh wlan stop hostednetwork
netsh wlan start hostednetwork
```

---

## SSH problems

### `Could not reach pi@... / No such host`

The Pi isn't on the network yet. Wait 20-30 seconds after powering it, then
`ping 192.168.137.100`. If `netsh wlan show hostednetwork` shows 1 client but the
ping fails, the Pi picked a different address: find it with `arp -a` and update
`pi.host` in `config.json`.

### `SSH authentication failed`

Wrong `pi.user` or `pi.password` in `config.json`. For key auth, set `pi.key_file`
and leave `pi.password` empty.

### SSH connects then drops after a few seconds

Wi-Fi power saving. On the Pi:

```bash
sudo iw dev wlan0 set power_save off
```

`pi/install_pi.sh` makes this permanent. To do it by hand, create
`/etc/NetworkManager/conf.d/wifi-powersave-off.conf` containing:

```
[connection]
wifi.powersave = 2
```

then `sudo systemctl restart NetworkManager`.

### `start_sender.sh is missing on the Pi`

Run `python tools/deploy_pi.py`.

---

## Stream problems

### `Receiver failed to bind port 8080`

A previous session still holds the port. Wait ~30 seconds, or change
`laptop.listen_port` in `config.json` and re-run `tools/deploy_pi.py` so the Pi
learns the new port.

### `handshake failed: the Pi is running an outdated sender`

The Pi still has the old pickle-based `demo_v2.py`. Fix it with:

```bash
python tools/deploy_pi.py
```

### Video never appears, GUI says "Waiting for the Pi to connect"

The sender isn't reaching the laptop. Read its log on the Pi:

```bash
ssh <user>@192.168.137.100 tail -n 40 /home/<user>/plant-detection/sender.log
```

| Message in the log | Meaning |
|---|---|
| `Connecting to 192.168.137.1:8080...` | Sender is alive, trying to reach the laptop |
| `Connected.` | Working; if you still see no video, check the camera |
| `Laptop not listening yet` | Press Start mission on the laptop first |
| `Network is unreachable` | Pi lost the network: `sudo nmcli con up "drone"` |
| `No camera could be opened` | Camera not detected, see below |

### `No camera could be opened`

Check the ribbon cable seating, then test the camera alone on the Pi:

```bash
libcamera-hello --list-cameras          # Pi Camera Module
python3 -c "import cv2; print(cv2.VideoCapture(0).isOpened())"   # USB webcam
```

Force a backend with `--camera picamera2` or `--camera opencv`.

### Frames arrive but the picture is torn or lagging

Reduce the bandwidth in `config.json` (`camera.jpeg_quality` 60, or
`camera.width/height` 320x240), then re-run `python tools/deploy_pi.py`.

---

## Detection problems

### Model file not found

`model.path` in `config.json` is relative to the repo root; the bundled weights
live at `models/best5.pt`.

### Pump never triggers, or nothing is detected

Watch the terminal for `[DETECTION]` lines. If none appear:

- The detector isn't confident enough. Lower `model.confidence` (try 0.4).
- `model.weed_class` must match a class the model actually has. On start-up the
  receiver prints `Model loaded. Classes: {...}` and warns if the name is unknown.
- `pump.min_detections` may be higher than the number of plants in frame.

### Inference is slow (YOLO time above 100 ms)

You are on the CPU. Check the start-up line `[YOLO] Using device:`. If it says
`cpu` but you have an NVIDIA GPU, install a CUDA build of torch:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### FPS is low but inference is fast

The bottleneck is the link. Lower the JPEG quality or resolution as above, and
confirm Wi-Fi power saving is off.
