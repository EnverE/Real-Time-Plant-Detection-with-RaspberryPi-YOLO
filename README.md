# Setup & Debug Guide

## Project overview

This system streams live video from a Raspberry Pi mounted on a drone to a laptop running a YOLO plant detection model over a local Wi-Fi network. No internet is required in the field.

```
Raspberry Pi (camera + sender) → Wi-Fi → Laptop (YOLO + GUI)
```

---

## Folder structure on the laptop

```
project/
├── gui_main.py               # Main GUI — run this to start
├── timestamp_with_yolo.py    # Receiver + YOLO logic
├── pi_connector.py           # SSH automation
├── stat_graph_generator.py   # Graph generator for test results
└── test_log_YYYYMMDD_HHMMSS.csv   # Auto-generated after each session
```

On the Pi (`/home/pi/Desktop/live_test/`):
```
demo_v2.py        # Sender — streams video to laptop
```

At home directory on Pi (`/home/pi/`):
```
start_sender.sh   # Auto-restart wrapper for demo_v2.py
```

---

## Requirements

### Laptop
```
Python 3.10+
pip install ultralytics opencv-python torch paramiko pillow matplotlib pandas
```

### Raspberry Pi
```
sudo apt install python3-picamera2 ffmpeg -y
pip install opencv-python --break-system-packages
```

---

## Step 1 — Set up the Wi-Fi hosted network on the laptop

The laptop acts as a Wi-Fi access point. The Pi connects to it.

1. Open **CMD as Administrator**
2. Run:
```cmd
netsh wlan set hostednetwork mode=allow ssid="drone" key="drone1234"
net start SharedAccess
netsh wlan start hostednetwork
```
3. Verify it started:
```cmd
netsh wlan show hostednetwork
```
Look for `Status: Started`

4. Confirm the laptop has `192.168.137.1`:
```cmd
ipconfig
```
Look for `Local Area Connection* 11` showing `192.168.137.1`

> **Note:** If `Local Area Connection* 11` shows `169.254.x.x` instead, run:
> ```cmd
> net stop SharedAccess
> net start SharedAccess
> netsh wlan stop hostednetwork
> netsh wlan start hostednetwork
> ```

---

## Step 2 — Connect the Pi to the hosted network

The Pi remembers the network after first setup. On first time only, SSH into the Pi using another network and run:

```bash
sudo nmcli dev wifi connect "drone" password "drone1234"
sudo nmcli con mod "drone" ipv4.addresses 192.168.137.100/24 ipv4.gateway 192.168.137.1 ipv4.method manual
sudo nmcli con up "drone"
```

After this the Pi always connects to `drone` automatically on boot and its IP is always `192.168.137.100`.

---

## Step 3 — Verify Pi is connected

After powering the Pi, wait 20 seconds then on the laptop:

```cmd
ping 192.168.137.100
```

Should reply. If not:
```cmd
netsh wlan show hostednetwork
```
Check `Number of clients` — if it shows 1, the Pi is connected but may have a different IP. Run `arp -a` to find it.

---

## Step 4 — Run the system

Simply run on the laptop:
```bash
python gui_main.py
```

Then click **Start Mission**. This automatically:
1. Starts the hosted network
2. SSHes into the Pi (`192.168.137.100`, user: `pi`, pass: `<set in config.json>`)
3. Kills any old sender process
4. Starts `start_sender.sh` on the Pi which runs `demo_v2.py`
5. Starts the receiver and YOLO model on the laptop
6. Stream begins

---

## Step 5 — Generate test graphs

After stopping the mission a CSV log is saved automatically in the project folder named `test_log_YYYYMMDD_HHMMSS.csv`.

To generate graphs:
```bash
python stat_graph_generator.py              # auto picks latest CSV
python stat_graph_generator.py test_log_x.csv  # specific file
```

---

## Common errors and fixes

### `[SSH] Failed: No such host`
The Pi is not connected to the hosted network yet.
- Check hosted network is running: `netsh wlan show hostednetwork`
- Ping the Pi: `ping 192.168.137.100`
- Wait 20-30 seconds after powering the Pi and try again

---

### `Network initialization failed: [WinError 10048]`
Port 8080 is already in use from a previous session that didn't close cleanly.
- Wait 30 seconds and try again (Windows releases the port automatically)
- Or restart the script

---

### `Stream ended or error: too many values to unpack`
The Pi is running the old sender that sends timestamps. Make sure `demo_v2.py` on the Pi sends only the frame:
```python
data = pickle.dumps(encoded_frame)  # no timestamp
```

---

### Video feed shows but metrics show 0
The `get_stats()` call is failing silently. Check that `timestamp_with_yolo.py` is the latest version with all stat keys present in `get_stats()`.

---

### Pump never triggers
Check in terminal for `[DETECTION]` lines. If none appear:
- The model is not detecting anything above the confidence threshold (0.65)
- Point camera at a plant and check terminal output
- Add debug print temporarily:
```python
print(f"[DEBUG] class: {class_name}, conf: {conf:.2f}, id: {box.id}")
```

---

### SSH connects but drops after a few seconds
Wi-Fi power saving is turning off the adapter. Run on the Pi:
```bash
sudo iw dev wlan0 set power_save off
```

Make it permanent:
```bash
sudo nano /etc/NetworkManager/conf.d/wifi-powersave-off.conf
```
Add:
```
[connection]
wifi.powersave = 2
```
Then:
```bash
sudo systemctl restart NetworkManager
```

---

### `OSError: [Errno 101] Network is unreachable` in sender log
The Pi cannot reach `192.168.137.1`. Check on the Pi:
```bash
ip addr show wlan0
ping 192.168.137.1
```
If wlan0 has no IP, reconnect:
```bash
sudo nmcli con up "drone"
```

---

### FPS is very low (under 10)
- Reduce JPEG quality in `demo_v2.py`: change `80` to `60`
- Reduce resolution: change `(640, 480)` to `(320, 240)`
- Check YOLO inference time in the GUI — if above 100ms the GPU is not being used, check `self.device = 0` in `timestamp_with_yolo.py`

---

### Hosted network won't start — `The wireless LAN interface is powered down`
The Wi-Fi radio is off. Run in CMD as Admin:
```cmd
netsh interface set interface "Wi-Fi 2" admin=enable
net stop wlansvc
net start wlansvc
netsh wlan start hostednetwork
```
Also check if airplane mode is on in Windows settings.

---

## Pi credentials reference

| Field | Value |
|---|---|
| Hostname | `raspberrypi.local` |
| Static IP | `192.168.137.100` |
| Username | `pi` |
| Password | `<set in config.json>` |
| Sender script | `/home/pi/Desktop/live_test/demo_v2.py` |
| Auto-restart script | `/home/pi/start_sender.sh` |
| Sender log | `/home/pi/Desktop/live_test/sender.log` |

---

## Checking the sender log on the Pi

If the stream isn't coming through, SSH into the Pi and check what the sender is doing:

```bash
ssh pi@192.168.137.100
cat /home/pi/Desktop/live_test/sender.log
```

Common messages and what they mean:

| Message | Meaning |
|---|---|
| `Connecting to 192.168.137.1:8080...` | Sender is running, trying to reach laptop |
| `Connected!` | Working correctly |
| `Network is unreachable` | Pi has no route to laptop — run `sudo nmcli con up "drone"` |
| `Connection refused` | Laptop receiver not started yet — start the GUI first |
| `nohup: failed to run command` | `start_sender.sh` is missing — recreate it (see below) |

---

## Recreating start_sender.sh on the Pi

If the shell script is missing:
```bash
nano /home/pi/start_sender.sh
```
Paste:
```bash
#!/bin/bash
while true; do
    echo "Starting sender..."
    python3 /home/pi/Desktop/live_test/demo_v2.py
    echo "Sender stopped. Restarting in 3s..."
    sleep 3
done
```
Save with `Ctrl+O`, exit with `Ctrl+X`, then:
```bash
chmod +x /home/pi/start_sender.sh
```
