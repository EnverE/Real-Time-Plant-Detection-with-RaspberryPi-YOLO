# Real-Time Plant Detection with Raspberry Pi + YOLO

A drone-mounted Raspberry Pi streams live camera frames over a local Wi-Fi link to
a laptop, which runs a YOLOv8 detector on every frame, tracks each plant so it is
only counted once, and triggers a (simulated) spray pump when a new one appears.
No internet connection is needed in the field.

```
Raspberry Pi + camera            Laptop
┌──────────────────┐  Wi-Fi   ┌────────────────────────────┐
│ pi/sender.py     │ ───────► │ receiver.py  → YOLO + track │
│ JPEG @ 640x480   │  TCP     │ gui_main.py  → live UI      │
└──────────────────┘  :8080   │ logs/*.csv   → metrics      │
                               └────────────────────────────┘
```

The GUI shows the annotated video plus network delay, jitter, inference time, FPS,
dropped frames and pump state, and writes a CSV of every frame so you can produce
performance charts afterwards.

---

## What's in here

```
gui_main.py            Tkinter control centre — this is the program you run
receiver.py            Listens for the Pi, decodes frames, runs YOLO, keeps stats
pi_connector.py        Starts/stops the sender on the Pi over SSH
config.py              Settings loader (config.json + environment variables)
config.example.json    Copy to config.json and edit

pi/sender.py           Runs ON THE PI: captures the camera and streams frames
pi/start_sender.sh     Auto-restart wrapper the GUI launches over SSH
pi/install_pi.sh       One-time dependency setup for the Pi

tools/deploy_pi.py     Copies the sender onto the Pi over SSH
tools/webcam_test.py   Try the model with no Pi at all (webcam or sample images)
tools/graph_report.py  Turns a session CSV into performance charts

scripts/start_hotspot.bat   Starts the Windows hosted network (run as admin)
models/best5.pt        Trained YOLOv8s weights (single class: "other")
testData/              52 sample images for offline testing
docs/                  Troubleshooting guide and Pixhawk wiring notes
```

---

## Requirements

**Laptop** — Python 3.10–3.12, and a GPU if you want real-time speed.
A CUDA GPU gives roughly 10–20 ms inference; on CPU expect 100 ms or more.

**Raspberry Pi** — Pi 4 or newer running Raspberry Pi OS Bookworm, with a Pi Camera
Module or a USB webcam.

**Wi-Fi** — any local network both machines share. The scripts assume the Windows
hosted-network setup (laptop `192.168.137.1`, Pi `192.168.137.100`), but a normal
router works too: just put the right addresses in `config.json`.

---

## Quick start — no Raspberry Pi needed

The fastest way to check that the model and your install work:

```bash
git clone https://github.com/EnverE/Real-Time-Plant-Detection-with-RaspberryPi-YOLO.git
cd Real-Time-Plant-Detection-with-RaspberryPi-YOLO
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python tools/webcam_test.py --source testData
```

That runs the bundled weights over the sample images. Use `--source 0` for your
webcam. Press `q` to close the preview.

---

## Full setup with the drone

### 1. Configure

```bash
copy config.example.json config.json
```

Then edit `config.json` — at minimum the `pi` section:

| Setting | Meaning |
|---|---|
| `pi.host` | Pi's address on the shared network (e.g. `192.168.137.100`) |
| `pi.user` / `pi.password` | Pi login. Leave `password` empty to use an SSH key instead |
| `pi.key_file` | Path to a private key, if you prefer key auth |
| `pi.remote_dir` | Where the sender gets installed on the Pi |
| `pi.auto_start` | `false` = don't SSH anywhere, just wait for a sender to connect |
| `laptop.hotspot_ip` | The laptop address the Pi streams **to** |
| `laptop.listen_port` | TCP port for the video link (default 8080) |
| `model.path` | Weights file, relative to the repo root |
| `model.confidence` | Detection threshold (default 0.7) |
| `model.weed_class` | Class name treated as a weed — `other` for the bundled model |
| `model.device` | `auto`, `cpu`, or a GPU index like `0` |
| `pump.duration_s` | How long the pump stays on per activation |
| `pump.min_detections` | Weeds that must be in frame before spraying |

`config.json` is git-ignored, so your password stays out of the repository. You can
also pass secrets by environment variable instead — `PLANT_PI_PASSWORD`,
`PLANT_PI_HOST`, `PLANT_MODEL_DEVICE`, and so on (see `config.py`).

### 2. Bring up the network

On Windows, right-click `scripts/start_hotspot.bat` → **Run as administrator**.
It creates the `drone` network (password `drone1234` — change it in the file) and
reports whether the laptop got `192.168.137.1`.

The first time only, point the Pi at that network. SSH in over any other connection
and run:

```bash
sudo nmcli dev wifi connect "drone" password "drone1234"
sudo nmcli con mod "drone" ipv4.addresses 192.168.137.100/24 ipv4.gateway 192.168.137.1 ipv4.method manual
sudo nmcli con up "drone"
```

From then on the Pi joins automatically at boot and always has the same address.
Check it with `ping 192.168.137.100`.

### 3. Install the sender on the Pi

From the laptop, with the Pi reachable:

```bash
python tools/deploy_pi.py --install
```

This copies `pi/sender.py`, `pi/start_sender.sh` and `pi/install_pi.sh` to the Pi,
writes a `sender_config.json` holding your laptop's address and camera settings,
and (with `--install`) installs picamera2/OpenCV and turns off Wi-Fi power saving.
Re-run it without `--install` whenever you change the sender.

### 4. Run a mission

```bash
python gui_main.py
```

Press **Start mission**. The laptop starts listening, SSHes into the Pi, launches
the sender, and the stream appears within a few seconds. **Stop mission** kills the
sender on the Pi and closes the CSV log. Closing the window does the same.

### 5. Look at the results

Each mission writes `logs/test_log_YYYYMMDD_HHMMSS.csv`. Turn the newest one into
charts (network delay, jitter, YOLO time, FPS, pipeline breakdown):

```bash
python tools/graph_report.py
```

**Save report** in the Statistics tab writes a text summary of the session.

---

## How it works

**The link.** The Pi opens a TCP connection to the laptop, sends a 4-byte
handshake, then one 16-byte header (`frame number`, `payload length`) plus JPEG
bytes per frame. Frame numbers let the receiver count dropped frames. If the
laptop isn't listening yet, or the link drops mid-flight, both sides retry — the
Pi reconnects every 3 seconds and the laptop keeps accepting.

**Detection.** Every frame goes through `model.track(...)` with ByteTrack, so each
plant keeps a stable ID across frames and is counted once no matter how long it
stays in view.

**The pump** fires when a *newly seen* plant appears and at least
`pump.min_detections` weeds are in frame. It stays on for `pump.duration_s` and
does not re-trigger while it is already spraying, so detections during a spray do
not inflate the activation count. Nothing is physically actuated yet — the pump is
a state flag plus counters. `docs/pixhawk/` holds the wiring and MAVLink notes for
connecting real hardware; `receiver._trigger_pump()` is the hook point.

**Metrics.** "Net delay" is the time to pull one frame off the socket, measured
from the first byte of its header — it is transfer time on the link, not a
clock-synchronised one-way latency. Jitter is the frame-to-frame change in that
value. All displayed values are rolling averages over the last 10 frames; the CSV
keeps every frame.

---

## Known limitations

- **The bundled model has one class** (`other`, trained on a tobacco dataset), so
  the "Total crops" and "Weed ratio" figures stay at 0. They come alive if you
  train a model with separate crop and weed classes and set `model.weed_class`.
- **The pump is simulated.** No GPIO or MAVLink command is sent.
- **The link is unencrypted and unauthenticated.** It is meant for an isolated
  ad-hoc network between two machines you own, not a shared or public Wi-Fi.
- **Area width/length in the Setup tab** are recorded in the report only; they do
  not affect detection or coverage calculations.

---

## Troubleshooting

See **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** — hosted network won't
start, SSH failures, port already in use, low FPS, pump never triggering, and how
to read the sender log on the Pi.
