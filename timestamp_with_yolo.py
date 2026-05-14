import cv2
import time
import socket
import pickle
import struct
import threading
import torch
from ultralytics import YOLO
import csv
from datetime import datetime


class Receiver:
    def __init__(self):
        self.HOST_IP = '0.0.0.0'
        self.PORT = 8080
        self.MODEL_PATH = "dataPath/train/weights/best5.pt"

        self.model = None
        self.server_socket = None
        self.conn = None
        self.is_running = False

        self.latest_frame = None
        self.weed_count = 0
        self._counted_track_ids = set()

        # --- Pump state ---
        self.pump_active = False
        self.pump_mode = "auto"
        self.spray_threshold = 1
        self.total_spray_activations = 0
        self.pump_active_since = None
        self.pump_duration = 2.0

        # --- Stats ---
        self.total_weed_detections = 0
        self._prev_weed_count = 0
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
        self.stats_network = {"min": float('inf'), "max": 0.0, "total": 0.0, "count": 0}
        self.stats_yolo    = {"min": float('inf'), "max": 0.0, "total": 0.0, "count": 0}
        self.stats_fps     = {"min": float('inf'), "max": 0.0, "total": 0.0, "count": 0}
        self.stats_jitter  = {"min": float('inf'), "max": 0.0, "total": 0.0, "count": 0}

        # --- Frame drop tracking ---
        self.frames_received = 0
        self.frames_dropped = 0
        self._last_frame_number = None

        # --- CSV logging ---
        self._log_file = None
        self._csv_writer = None

        self.device = 0
        print(f"Using device: {self.device}")

        print(f"Loading YOLO model from {self.MODEL_PATH}...")
        try:
            self.model = YOLO(self.MODEL_PATH)
            print("Model loaded successfully!")
        except Exception as e:
            print(f"Failed to load model: {e}")

    # ------------------------------------------------------------------ helpers
    def _update_stat(self, stat, value):
        stat["min"]    = min(stat["min"], value)
        stat["max"]    = max(stat["max"], value)
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
        filename = f"test_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self._log_file = open(filename, 'w', newline='')
        self._csv_writer = csv.writer(self._log_file)
        self._csv_writer.writerow([
            "timestamp", "network_ms", "yolo_ms", "fps",
            "jitter_ms", "frames_dropped", "packet_loss_pct", "detections"
        ])
        print(f"[LOG] Logging to {filename}")

    def _log_frame(self):
        if self._csv_writer is not None:
            self._csv_writer.writerow([
                round(time.time(), 3),
                round(self.network_delay_ms, 2),
                round(self.yolo_ms, 2),
                round(self.fps, 2),
                round(self.jitter_ms, 2),
                self.frames_dropped,
                round(self.packet_loss_pct, 2),
                self.weed_count
            ])

    # ------------------------------------------------------------------ network
    def initialize(self):
        if self.model is None:
            print("Cannot start: Model failed to load.")
            return False
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.HOST_IP, self.PORT))
            self.server_socket.listen(1)
            print(f"Listening for Pi on port {self.PORT}...")
            self.is_running = True
            self._start_logging()
            threading.Thread(target=self._receive_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"Network initialization failed: {e}")
            return False

    def _receive_loop(self):
        try:
            self.conn, addr = self.server_socket.accept()
            print(f"Connected to Pi at {addr}")

            data = b""
            payload_size = struct.calcsize("Q")

            while self.is_running:

                # Start timer BEFORE reading anything for this frame
                recv_start = time.time()

                # Read header
                while len(data) < payload_size:
                    packet = self.conn.recv(4 * 1024)
                    if not packet:
                        break
                    data += packet
                if not data:
                    break

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                # Read frame body
                while len(data) < msg_size:
                    data += self.conn.recv(4 * 1024)

                # Stop timer after full frame received
                recv_end = time.time()
                raw_delay = (recv_end - recv_start) * 1000

                # Smooth and track network delay
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

                # Decode frame — unpack frame number for drop detection
                frame_data = data[:msg_size]
                data = data[msg_size:]
                payload = pickle.loads(frame_data)

                # Support both (frame_number, frame) and just frame
                if isinstance(payload, tuple):
                    frame_number, encoded_frame = payload
                    self.frames_received += 1
                    if self._last_frame_number is not None:
                        gap = frame_number - self._last_frame_number - 1
                        if gap > 0:
                            self.frames_dropped += gap
                            print(f"[NET] Dropped {gap} frame(s) at frame #{frame_number}")
                    self._last_frame_number = frame_number
                else:
                    encoded_frame = payload
                    self.frames_received += 1

                frame = cv2.imdecode(encoded_frame, cv2.IMREAD_COLOR)

                # YOLO inference
                yolo_start = time.time()
                results = self.model.track(
                    frame, verbose=False, device=self.device,
                    conf=0.7, persist=True, tracker="bytetrack.yaml"
                )
                yolo_end = time.time()
                raw_yolo = (yolo_end - yolo_start) * 1000

                self._yolo_samples.append(raw_yolo)
                if len(self._yolo_samples) > self.SMOOTH:
                    self._yolo_samples.pop(0)
                self.yolo_ms = sum(self._yolo_samples) / len(self._yolo_samples)
                self._update_stat(self.stats_yolo, raw_yolo)

                # FPS
                now = time.time()
                if self._last_frame_time is not None:
                    raw_fps = 1.0 / (now - self._last_frame_time)
                    self._fps_samples.append(raw_fps)
                    if len(self._fps_samples) > self.SMOOTH:
                        self._fps_samples.pop(0)
                    self.fps = sum(self._fps_samples) / len(self._fps_samples)
                    self._update_stat(self.stats_fps, raw_fps)
                self._last_frame_time = now

                # Detection
                frame = results[0].plot()
                boxes = results[0].boxes
                names = self.model.names

                new_weeds = 0
                current_weed_count = 0

                for box in boxes:
                    class_id   = int(box.cls[0])
                    class_name = names[class_id].lower()
                    conf       = float(box.conf[0])

                    if class_name == "other":
                        if box.id is not None:
                            track_id = int(box.id[0].item())
                            if track_id in self._counted_track_ids:
                                current_weed_count += 1
                            elif conf >= 0.4:
                                self._counted_track_ids.add(track_id)
                                current_weed_count += 1
                                new_weeds += 1
                                print(f"[DETECTION] New weed #{track_id} (conf: {conf:.2f})")
                        else:
                            if conf >= 0.5:
                                current_weed_count += 1

                self.weed_count = current_weed_count
                self.total_weed_detections += new_weeds

                # Pump fires only on genuinely new plants
                if self.pump_mode == "auto" and new_weeds > 0:
                    self._trigger_pump()

                # Auto turn off pump after duration
                if self.pump_active and self.pump_active_since is not None:
                    if time.time() - self.pump_active_since >= self.pump_duration:
                        self.pump_active = False

                # Overlay metrics on frame
                cv2.putText(frame, f"Net: {self.network_delay_ms:.1f} ms",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 165, 0), 2)
                cv2.putText(frame, f"YOLO: {self.yolo_ms:.1f} ms",
                            (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.putText(frame, f"Jitter: {self.jitter_ms:.1f} ms",
                            (10, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 200, 255), 2)
                cv2.putText(frame, f"FPS: {self.fps:.1f}",
                            (10, 126), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"Pump: {'ACTIVE' if self.pump_active else 'off'}",
                            (10, 158), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 255, 100) if self.pump_active else (150, 150, 150), 2)

                self.latest_frame = frame
                self._log_frame()

        except Exception as e:
            print(f"Stream ended or error: {e}")
        finally:
            self.stop()

    # ------------------------------------------------------------------ pump
    def _trigger_pump(self):
        if not self.pump_active:
            self.pump_active = True
            self.pump_active_since = time.time()
            self.total_spray_activations += 1
            print(f"[PUMP] Triggered (activation #{self.total_spray_activations})")
            # --- Future Pixhawk integration point ---
            # from pymavlink import mavutil
            # master.mav.command_long_send(...)

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
        net_min    = self.stats_network["min"] if self.stats_network["count"] > 0 else 0.0
        yolo_min   = self.stats_yolo["min"]    if self.stats_yolo["count"] > 0    else 0.0
        fps_min    = self.stats_fps["min"]      if self.stats_fps["count"] > 0    else 0.0
        jitter_min = self.stats_jitter["min"]   if self.stats_jitter["count"] > 0 else 0.0

        return {
            # Live smoothed values
            "network_delay_ms": self.network_delay_ms,
            "yolo_ms":          self.yolo_ms,
            "fps":              self.fps,
            "jitter_ms":        self.jitter_ms,

            # Network delay stats
            "net_min":  net_min,
            "net_max":  self.stats_network["max"],
            "net_avg":  self._avg(self.stats_network),

            # YOLO stats
            "yolo_min": yolo_min,
            "yolo_max": self.stats_yolo["max"],
            "yolo_avg": self._avg(self.stats_yolo),

            # FPS stats
            "fps_min":  fps_min,
            "fps_max":  self.stats_fps["max"],
            "fps_avg":  self._avg(self.stats_fps),

            # Jitter stats
            "jitter_min": jitter_min,
            "jitter_max": self.stats_jitter["max"],
            "jitter_avg": self._avg(self.stats_jitter),

            # Frame drop
            "frames_received": self.frames_received,
            "frames_dropped":  self.frames_dropped,
            "packet_loss_pct": self.packet_loss_pct,

            # Detection
            "weed_count":  self.weed_count,
            "total_weeds": self.total_weed_detections,
            "total_crops": self.total_crop_detections,

            # Pump
            "pump_active":       self.pump_active,
            "pump_mode":         self.pump_mode,
            "spray_activations": self.total_spray_activations,
        }

    # ------------------------------------------------------------------ stop
    def stop(self):
        self.is_running = False
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        if self._log_file:
            try:
                self._log_file.close()
                print("[LOG] Log file saved.")
            except:
                pass
        print("Receiver stopped.")