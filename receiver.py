"""
Laptop-side receiver.

Listens for the Raspberry Pi sender (pi/sender.py), decodes each incoming JPEG
frame, runs YOLO tracking on it and keeps the running statistics that the GUI
displays and the CSV log records.

Wire protocol (see pi/sender.py for the other half):

    on connect:  b"PDS1"                       -- 4-byte handshake
    per frame:   !QQ  frame_number, length     -- 16-byte header
                 <length> bytes of JPEG data

The old protocol pickled a numpy array over the socket, which meant the laptop
executed whatever the sender sent it. Plain JPEG bytes cannot do that, so if an
outdated sender connects the handshake fails with a clear message instead.
"""

import csv
import socket
import struct
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO

import config

HANDSHAKE = b"PDS1"
HEADER = struct.Struct("!QQ")


class Receiver:
    def __init__(self, cfg=None):
        self.cfg = cfg or config.load_config()

        self.HOST_IP = self.cfg["laptop"]["listen_host"]
        self.PORT = self.cfg["laptop"]["listen_port"]
        self.MODEL_PATH = config.resolve_path(self.cfg["model"]["path"])

        self.model = None
        self.model_error = None
        self.server_socket = None
        self.conn = None
        self.is_running = False
        self.connection_state = "idle"   # idle | waiting | connected | error

        self.latest_frame = None
        self.weed_count = 0
        self._counted_track_ids = set()
        self._counted_crop_ids = set()

        # --- Pump state ---
        self.pump_active = False
        self.pump_mode = self.cfg["pump"]["mode"]
        self.spray_threshold = int(self.cfg["pump"]["min_detections"])
        self.total_spray_activations = 0
        self.pump_active_since = None
        self.pump_duration = float(self.cfg["pump"]["duration_s"])

        # --- Stats ---
        self.total_weed_detections = 0
        self.total_crop_detections = 0
        self.yolo_ms = 0.0
        self.fps = 0.0
        self._last_frame_time = None
        self.network_delay_ms = 0.0
        self.jitter_ms = 0.0

        self._delay_samples = []
        self._yolo_samples = []
        self._fps_samples = []
        self._jitter_samples = []
        self._last_frame_delay = None
        self.SMOOTH = 10

        # --- Min/Max/Avg tracking ---
        self.stats_network = {"min": float("inf"), "max": 0.0, "total": 0.0, "count": 0}
        self.stats_yolo = {"min": float("inf"), "max": 0.0, "total": 0.0, "count": 0}
        self.stats_fps = {"min": float("inf"), "max": 0.0, "total": 0.0, "count": 0}
        self.stats_jitter = {"min": float("inf"), "max": 0.0, "total": 0.0, "count": 0}

        # --- Frame drop tracking ---
        self.frames_received = 0
        self.frames_dropped = 0
        self._last_frame_number = None

        # --- CSV logging ---
        self._log_file = None
        self._csv_writer = None
        self.log_path = None

        self.device = config.device_for(self.cfg["model"]["device"])
        self.weed_class = str(self.cfg["model"]["weed_class"]).lower()
        print(f"[YOLO] Using device: {self.device}")

        self._load_model()

    # ------------------------------------------------------------------ model
    def _load_model(self):
        if not self.MODEL_PATH.exists():
            self.model_error = (
                f"Model file not found: {self.MODEL_PATH}\n"
                "Check model.path in config.json."
            )
            print(f"[YOLO] {self.model_error}")
            return

        print(f"[YOLO] Loading model from {self.MODEL_PATH} ...")
        try:
            self.model = YOLO(str(self.MODEL_PATH))
            print(f"[YOLO] Model loaded. Classes: {self.model.names}")
            known = {str(n).lower() for n in self.model.names.values()}
            if self.weed_class not in known:
                print(
                    f"[YOLO] Warning: model.weed_class '{self.weed_class}' is not one of "
                    f"{sorted(known)}, so nothing will ever be counted as a weed."
                )
        except Exception as exc:
            self.model_error = f"Failed to load model: {exc}"
            print(f"[YOLO] {self.model_error}")

    # ------------------------------------------------------------------ helpers
    def _update_stat(self, stat, value):
        stat["min"] = min(stat["min"], value)
        stat["max"] = max(stat["max"], value)
        stat["total"] += value
        stat["count"] += 1

    def _avg(self, stat):
        return stat["total"] / stat["count"] if stat["count"] > 0 else 0.0

    @property
    def packet_loss_pct(self):
        total = self.frames_received + self.frames_dropped
        if total == 0:
            return 0.0
        return (self.frames_dropped / total) * 100

    def _start_logging(self):
        log_dir = config.resolve_path(self.cfg["logging"]["csv_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / f"test_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._log_file = open(self.log_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._log_file)
        self._csv_writer.writerow([
            "timestamp", "network_ms", "yolo_ms", "fps",
            "jitter_ms", "frames_dropped", "packet_loss_pct", "detections",
        ])
        print(f"[LOG] Logging to {self.log_path}")

    def _log_frame(self):
        if self._csv_writer is None:
            return
        self._csv_writer.writerow([
            round(time.time(), 3),
            round(self.network_delay_ms, 2),
            round(self.yolo_ms, 2),
            round(self.fps, 2),
            round(self.jitter_ms, 2),
            self.frames_dropped,
            round(self.packet_loss_pct, 2),
            self.weed_count,
        ])
        self._log_file.flush()

    # ------------------------------------------------------------------ network
    def _reset_session(self):
        """Clear counters so a restarted mission does not inherit old numbers."""
        self.latest_frame = None
        self.weed_count = 0
        self._counted_track_ids.clear()
        self._counted_crop_ids.clear()

        self.total_weed_detections = 0
        self.total_crop_detections = 0
        self.total_spray_activations = 0
        self.pump_active = False
        self.pump_active_since = None

        self.yolo_ms = self.fps = self.network_delay_ms = self.jitter_ms = 0.0
        self._delay_samples.clear()
        self._yolo_samples.clear()
        self._fps_samples.clear()
        self._jitter_samples.clear()
        self._last_frame_delay = None
        self._last_frame_time = None

        for stat in (self.stats_network, self.stats_yolo, self.stats_fps, self.stats_jitter):
            stat.update({"min": float("inf"), "max": 0.0, "total": 0.0, "count": 0})

        self.frames_received = 0
        self.frames_dropped = 0
        self._last_frame_number = None

        # Drop tracker state too, otherwise plants from the last mission keep
        # their IDs and are never counted as new.
        try:
            for tracker in self.model.predictor.trackers:
                tracker.reset()
        except (AttributeError, TypeError):
            pass

    def initialize(self):
        """Bind the listening socket and start the receive thread."""
        if self.model is None:
            print(f"[NET] Cannot start: {self.model_error}")
            return False
        self._reset_session()
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.HOST_IP, self.PORT))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            print(f"[NET] Listening for the Pi on port {self.PORT} ...")
            self.is_running = True
            self.connection_state = "waiting"
            self._start_logging()
            threading.Thread(target=self._accept_loop, daemon=True).start()
            return True
        except OSError as exc:
            self.connection_state = "error"
            print(f"[NET] Network initialization failed: {exc}")
            return False

    def _accept_loop(self):
        """Accept connections until stopped, so the Pi can reconnect freely."""
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            print(f"[NET] Pi connected from {addr[0]}")
            self.conn = conn
            self.connection_state = "connected"
            try:
                self._stream_loop(conn)
            except (ConnectionError, OSError, ValueError) as exc:
                print(f"[NET] Stream ended: {exc}")
            except Exception as exc:                      # keep the thread alive
                print(f"[NET] Unexpected stream error: {exc}")
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                self.conn = None
                if self.is_running:
                    self.connection_state = "waiting"
                    self._last_frame_number = None
                    self._last_frame_time = None
                    print("[NET] Waiting for the Pi to reconnect ...")

    def _recv_exact(self, conn, n):
        """Read exactly n bytes, or raise if the peer goes away."""
        chunks = []
        remaining = n
        while remaining > 0:
            packet = conn.recv(min(remaining, 65536))
            if not packet:
                raise ConnectionError("sender closed the connection")
            chunks.append(packet)
            remaining -= len(packet)
        return b"".join(chunks)

    def _stream_loop(self, conn):
        magic = self._recv_exact(conn, len(HANDSHAKE))
        if magic != HANDSHAKE:
            raise ValueError(
                "handshake failed: the Pi is running an outdated sender. "
                "Redeploy it with: python tools/deploy_pi.py"
            )

        while self.is_running:
            # Block until the first byte of the next frame arrives; the transfer
            # timer starts there, so idle time between frames is not counted as
            # network delay.
            first = conn.recv(1)
            if not first:
                raise ConnectionError("sender closed the connection")
            recv_start = time.time()

            header = first + self._recv_exact(conn, HEADER.size - 1)
            frame_number, length = HEADER.unpack(header)
            if length == 0 or length > 32 * 1024 * 1024:
                raise ValueError(f"implausible frame size: {length} bytes")

            payload = self._recv_exact(conn, length)
            raw_delay = (time.time() - recv_start) * 1000

            self._track_network(raw_delay)
            self._track_frame_number(frame_number)

            frame = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                print(f"[NET] Frame #{frame_number} failed to decode, skipping.")
                continue

            self._process_frame(frame)

    def _track_network(self, raw_delay):
        self._delay_samples.append(raw_delay)
        if len(self._delay_samples) > self.SMOOTH:
            self._delay_samples.pop(0)
        self.network_delay_ms = sum(self._delay_samples) / len(self._delay_samples)
        self._update_stat(self.stats_network, raw_delay)

        # Jitter = absolute change in delay between consecutive frames
        if self._last_frame_delay is not None:
            raw_jitter = abs(raw_delay - self._last_frame_delay)
            self._jitter_samples.append(raw_jitter)
            if len(self._jitter_samples) > self.SMOOTH:
                self._jitter_samples.pop(0)
            self.jitter_ms = sum(self._jitter_samples) / len(self._jitter_samples)
            self._update_stat(self.stats_jitter, raw_jitter)
        self._last_frame_delay = raw_delay

    def _track_frame_number(self, frame_number):
        self.frames_received += 1
        if self._last_frame_number is not None:
            gap = frame_number - self._last_frame_number - 1
            if gap > 0:
                self.frames_dropped += gap
                print(f"[NET] Dropped {gap} frame(s) before frame #{frame_number}")
        self._last_frame_number = frame_number

    # ------------------------------------------------------------------ inference
    def _process_frame(self, frame):
        yolo_start = time.time()
        results = self.model.track(
            frame,
            verbose=False,
            device=self.device,
            conf=float(self.cfg["model"]["confidence"]),
            persist=True,
            tracker=self.cfg["model"]["tracker"],
        )
        raw_yolo = (time.time() - yolo_start) * 1000

        self._yolo_samples.append(raw_yolo)
        if len(self._yolo_samples) > self.SMOOTH:
            self._yolo_samples.pop(0)
        self.yolo_ms = sum(self._yolo_samples) / len(self._yolo_samples)
        self._update_stat(self.stats_yolo, raw_yolo)

        now = time.time()
        if self._last_frame_time is not None:
            elapsed = now - self._last_frame_time
            if elapsed > 0:
                raw_fps = 1.0 / elapsed
                self._fps_samples.append(raw_fps)
                if len(self._fps_samples) > self.SMOOTH:
                    self._fps_samples.pop(0)
                self.fps = sum(self._fps_samples) / len(self._fps_samples)
                self._update_stat(self.stats_fps, raw_fps)
        self._last_frame_time = now

        annotated = results[0].plot()
        names = self.model.names

        new_weeds = 0
        current_weed_count = 0

        for box in results[0].boxes:
            class_name = str(names[int(box.cls[0])]).lower()
            conf = float(box.conf[0])
            track_id = int(box.id[0].item()) if box.id is not None else None

            if class_name == self.weed_class:
                current_weed_count += 1
                if track_id is not None and track_id not in self._counted_track_ids:
                    self._counted_track_ids.add(track_id)
                    new_weeds += 1
                    print(f"[DETECTION] New weed #{track_id} (conf: {conf:.2f})")
            else:
                # Anything the model recognizes that is not the weed class is
                # treated as crop. The bundled model has a single class, so this
                # stays at 0 until you train a multi-class model.
                if track_id is not None and track_id not in self._counted_crop_ids:
                    self._counted_crop_ids.add(track_id)
                    self.total_crop_detections += 1

        self.weed_count = current_weed_count
        self.total_weed_detections += new_weeds

        # Fire only on genuinely new plants, and only once enough of them are
        # in view (the "min detections to spray" slider in the GUI).
        if (self.pump_mode == "auto"
                and new_weeds > 0
                and current_weed_count >= self.spray_threshold):
            self._trigger_pump()

        if self.pump_active and self.pump_active_since is not None:
            if time.time() - self.pump_active_since >= self.pump_duration:
                self.pump_active = False

        self._draw_overlay(annotated)
        self.latest_frame = annotated
        self._log_frame()

    def _draw_overlay(self, frame):
        lines = [
            (f"Net: {self.network_delay_ms:.1f} ms", (255, 165, 0)),
            (f"YOLO: {self.yolo_ms:.1f} ms", (255, 255, 0)),
            (f"Jitter: {self.jitter_ms:.1f} ms", (100, 200, 255)),
            (f"FPS: {self.fps:.1f}", (0, 255, 0)),
            (f"Pump: {'ACTIVE' if self.pump_active else 'off'}",
             (0, 255, 100) if self.pump_active else (150, 150, 150)),
        ]
        for i, (text, color) in enumerate(lines):
            cv2.putText(frame, text, (10, 30 + i * 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    # ------------------------------------------------------------------ pump
    def _trigger_pump(self):
        if not self.pump_active:
            self.pump_active = True
            self.pump_active_since = time.time()
            self.total_spray_activations += 1
            print(f"[PUMP] Triggered (activation #{self.total_spray_activations})")
            # --- Pixhawk integration point ---
            # See docs/pixhawk/README.md. The pump is currently simulated:
            # nothing is actuated, only the state and counters change.

    def trigger_pump_manual(self):
        self._trigger_pump()

    def set_pump_mode(self, mode):
        self.pump_mode = mode
        print(f"[PUMP] Mode set to: {mode}")

    def set_spray_threshold(self, value):
        self.spray_threshold = int(value)

    # ------------------------------------------------------------------ getters
    def get_frame(self):
        return self.latest_frame, self.weed_count

    def get_stats(self):
        def _min(stat):
            return stat["min"] if stat["count"] > 0 else 0.0

        return {
            # Live smoothed values
            "network_delay_ms": self.network_delay_ms,
            "yolo_ms": self.yolo_ms,
            "fps": self.fps,
            "jitter_ms": self.jitter_ms,

            # Network delay stats
            "net_min": _min(self.stats_network),
            "net_max": self.stats_network["max"],
            "net_avg": self._avg(self.stats_network),

            # YOLO stats
            "yolo_min": _min(self.stats_yolo),
            "yolo_max": self.stats_yolo["max"],
            "yolo_avg": self._avg(self.stats_yolo),

            # FPS stats
            "fps_min": _min(self.stats_fps),
            "fps_max": self.stats_fps["max"],
            "fps_avg": self._avg(self.stats_fps),

            # Jitter stats
            "jitter_min": _min(self.stats_jitter),
            "jitter_max": self.stats_jitter["max"],
            "jitter_avg": self._avg(self.stats_jitter),

            # Frame drop
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
            "packet_loss_pct": self.packet_loss_pct,

            # Detection
            "weed_count": self.weed_count,
            "total_weeds": self.total_weed_detections,
            "total_crops": self.total_crop_detections,

            # Pump
            "pump_active": self.pump_active,
            "pump_mode": self.pump_mode,
            "spray_activations": self.total_spray_activations,

            # Link
            "connection_state": self.connection_state,
        }

    # ------------------------------------------------------------------ stop
    def stop(self):
        self.is_running = False
        self.connection_state = "idle"
        for sock in (self.conn, self.server_socket):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self.conn = None
        self.server_socket = None
        if self._log_file is not None:
            try:
                self._log_file.close()
                print(f"[LOG] Log saved to {self.log_path}")
            except OSError:
                pass
            self._log_file = None
            self._csv_writer = None
        print("[NET] Receiver stopped.")
