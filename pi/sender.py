#!/usr/bin/env python3
"""
Raspberry Pi camera sender.

Captures frames, JPEG-encodes them and streams them to the laptop running
receiver.py. Reconnects by itself if the laptop is not up yet or the link
drops mid-flight.

Wire protocol (the receiver half is in receiver.py):

    on connect:  b"PDS1"                       -- 4-byte handshake
    per frame:   !QQ  frame_number, length     -- 16-byte header
                 <length> bytes of JPEG data

Camera backend: picamera2 if available (Pi Camera Module), otherwise OpenCV
(USB webcam). Force one with --camera picamera2|opencv.

Settings come from sender_config.json next to this file if it exists, and
command line flags override that. tools/deploy_pi.py writes that file for you.

    python3 sender.py --host 192.168.137.1 --port 8080
"""

import argparse
import json
import socket
import struct
import sys
import time
from pathlib import Path

import cv2

HANDSHAKE = b"PDS1"
HEADER = struct.Struct("!QQ")
CONFIG_FILE = Path(__file__).resolve().parent / "sender_config.json"

DEFAULTS = {
    "host": "192.168.137.1",
    "port": 8080,
    "width": 640,
    "height": 480,
    "fps": 30,
    "jpeg_quality": 80,
    "camera": "auto",
}


# ---------------------------------------------------------------- cameras
class PiCamera2Source:
    name = "picamera2"

    def __init__(self, width, height, fps):
        from picamera2 import Picamera2

        self.cam = Picamera2()
        cfg = self.cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": float(fps)},
        )
        self.cam.configure(cfg)
        self.cam.start()
        time.sleep(1.0)  # let auto-exposure settle

    def read(self):
        return self.cam.capture_array()

    def close(self):
        try:
            self.cam.stop()
            self.cam.close()
        except Exception:
            pass


class OpenCVSource:
    name = "opencv"

    def __init__(self, width, height, fps):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise RuntimeError("no camera on /dev/video0")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self):
        self.cap.release()


def open_camera(preference, width, height, fps):
    order = {
        "auto": [PiCamera2Source, OpenCVSource],
        "picamera2": [PiCamera2Source],
        "opencv": [OpenCVSource],
    }[preference]

    errors = []
    for source in order:
        try:
            cam = source(width, height, fps)
            print(f"[CAM] Using {source.name} at {width}x{height} @ {fps} fps")
            return cam
        except Exception as exc:
            errors.append(f"{source.name}: {exc}")

    raise SystemExit("[CAM] No camera could be opened.\n  " + "\n  ".join(errors))


# ---------------------------------------------------------------- streaming
def stream_once(cam, host, port, quality, fps):
    """Connect to the laptop and stream until the link drops."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    print(f"[NET] Connecting to {host}:{port} ...")
    sock.connect((host, port))
    sock.settimeout(None)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.sendall(HANDSHAKE)
    print("[NET] Connected.")

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    frame_interval = 1.0 / fps if fps > 0 else 0.0
    frame_number = 0
    reported = time.time()
    sent_since_report = 0

    try:
        while True:
            loop_start = time.time()

            frame = cam.read()
            if frame is None:
                print("[CAM] Dropped a frame from the camera.")
                time.sleep(0.05)
                continue

            ok, encoded = cv2.imencode(".jpg", frame, encode_params)
            if not ok:
                print("[CAM] JPEG encoding failed, skipping frame.")
                continue

            payload = encoded.tobytes()
            sock.sendall(HEADER.pack(frame_number, len(payload)) + payload)
            frame_number += 1
            sent_since_report += 1

            if time.time() - reported >= 10:
                print(f"[NET] {sent_since_report / (time.time() - reported):.1f} fps sent")
                reported = time.time()
                sent_since_report = 0

            # Pace the loop so we do not outrun the requested frame rate
            spare = frame_interval - (time.time() - loop_start)
            if spare > 0:
                time.sleep(spare)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def load_settings():
    settings = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            settings.update(json.loads(CONFIG_FILE.read_text()))
            print(f"[CFG] Loaded {CONFIG_FILE.name}")
        except json.JSONDecodeError as exc:
            print(f"[CFG] Ignoring malformed {CONFIG_FILE.name}: {exc}")

    parser = argparse.ArgumentParser(description="Stream Pi camera frames to the laptop.")
    parser.add_argument("--host", default=settings["host"], help="laptop IP address")
    parser.add_argument("--port", type=int, default=settings["port"])
    parser.add_argument("--width", type=int, default=settings["width"])
    parser.add_argument("--height", type=int, default=settings["height"])
    parser.add_argument("--fps", type=int, default=settings["fps"])
    parser.add_argument("--quality", type=int, default=settings["jpeg_quality"],
                        help="JPEG quality 1-100; lower means less bandwidth")
    parser.add_argument("--camera", default=settings["camera"],
                        choices=["auto", "picamera2", "opencv"])
    parser.add_argument("--retry", type=float, default=3.0,
                        help="seconds to wait before reconnecting")
    return parser.parse_args()


def main():
    args = load_settings()
    cam = open_camera(args.camera, args.width, args.height, args.fps)

    try:
        while True:
            try:
                stream_once(cam, args.host, args.port, args.quality, args.fps)
            except KeyboardInterrupt:
                raise
            except (ConnectionRefusedError, socket.timeout, TimeoutError):
                print(f"[NET] Laptop not listening yet. Retrying in {args.retry:.0f}s ...")
            except OSError as exc:
                print(f"[NET] Link lost ({exc}). Retrying in {args.retry:.0f}s ...")
            time.sleep(args.retry)
    except KeyboardInterrupt:
        print("\n[EXIT] Stopped by user.")
    finally:
        cam.close()


if __name__ == "__main__":
    sys.exit(main())
