# Real-Time Plant Detection with Raspberry Pi + YOLO

# Important!
This is a simple script that we are using to develop our student project this is still work in progress and will be updated regularly, Our current model is only trained to **detect tobacco plants specifically!!** 

Stream live video from a **Raspberry Pi 3** with **Pi Camera v2** over Wi-Fi to a **Windows laptop**, and run **YOLO object detection** to identify plants in real time.

Built for edge AI prototyping, agriculture monitoring, or educational computer vision projects.

---

## Features

- **Low-latency video streaming** from Raspberry Pi → Windows via UDP
- **Hardware-accelerated H.264 encoding** on Pi (using `rpicam-vid`)
- **YOLOv8 plant detection** on Windows (supports custom models)
- **Frame skipping** to balance performance & accuracy
- Works on **Raspberry Pi OS Bookworm** (2024+) with modern camera stack

---

## Hardware Requirements

- Raspberry Pi 3 (or newer)
- Raspberry Pi Camera Module v2
- Windows laptop (10/11) with Python
- Both devices on the **same Wi-Fi network** 

---

## Tips for Best Performance
Use 640×480 @ 15 FPS, 2 Mbps for stable Wi-Fi streaming on Pi 3
Ensure good lighting — YOLO works better than high bitrate!
Keep both devices close to the Wi-Fi router (Pi 3 uses 2.4 GHz only)
