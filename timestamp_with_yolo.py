import cv2
import time
import socket
import pickle
import struct
import threading
import numpy as np
from ultralytics import YOLO


class Receiver:
    def __init__(self):
        # --- Configuration ---
        self.HOST_IP = '0.0.0.0'
        self.PORT = 8080
        self.MODEL_PATH = "dataPath/train/weights/best3.pt"

        # --- State Variables ---
        self.model = None
        self.server_socket = None
        self.conn = None
        self.is_running = False

        # These are fetched by the GUI
        self.latest_frame = None
        self.weed_count = 0

        # Load the YOLO model right when the class is created
        print(f"Loading YOLO model from {self.MODEL_PATH}...")
        try:
            self.model = YOLO(self.MODEL_PATH)
            print("✅ Model loaded successfully!")
        except Exception as e:
            print(f"❌ Failed to load model: {e}")

    def initialize(self):
        """Starts the server and launches the background receiving thread."""
        if self.model is None:
            print("Cannot start: Model failed to load.")
            return False

        try:
            # Setup Network Server
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.HOST_IP, self.PORT))
            self.server_socket.listen(1)
            print(f"\nListening for Pi on port {self.PORT}...")

            self.is_running = True

            # Start the network loop in a background thread so it doesn't freeze the GUI
            threading.Thread(target=self._receive_loop, daemon=True).start()
            return True

        except Exception as e:
            print(f"Network initialization failed: {e}")
            return False

    def _receive_loop(self):
        """The background loop that handles TCP bytes, YOLO, and Latency math."""
        try:
            # Block and wait for the Pi to connect
            self.conn, addr = self.server_socket.accept()
            print(f"Connected to Pi at {addr}")

            data = b""
            payload_size = struct.calcsize("Q")

            while self.is_running:
                # 1. Receive the message size
                while len(data) < payload_size:
                    packet = self.conn.recv(4 * 1024)
                    if not packet: break
                    data += packet
                if not data: break

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                # 2. Receive the actual payload (timestamp + frame)
                while len(data) < msg_size:
                    data += self.conn.recv(4 * 1024)

                frame_data = data[:msg_size]
                data = data[msg_size:]

                # 3. Extract the timestamp and compressed frame
                send_time, encoded_frame = pickle.loads(frame_data)

                # 4. Decode the JPEG back into an OpenCV image
                frame = cv2.imdecode(encoded_frame, cv2.IMREAD_COLOR)

                # ==========================================
                # MEASUREMENT 1: NETWORK DELAY
                # ==========================================
                receive_time = time.time()
                network_delay_ms = (receive_time - send_time) * 1000

                # ==========================================
                # YOLO INFERENCE
                # ==========================================
                results = self.model(frame, verbose=False)  # verbose=False keeps terminal clean

                # Draw the bounding boxes onto the frame
                frame = results[0].plot()

                # Count how many objects YOLO found
                current_weed_count = len(results[0].boxes)

                # ==========================================
                # MEASUREMENT 2: TOTAL DELAY
                # ==========================================
                finish_time = time.time()
                total_delay_ms = (finish_time - send_time) * 1000
                yolo_processing_ms = total_delay_ms - network_delay_ms

                # Overlay the stats on the video feed
                cv2.putText(frame, f"Net Delay: {network_delay_ms:.1f} ms", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 165, 0), 2)

                cv2.putText(frame, f"YOLO Time: {yolo_processing_ms:.1f} ms", (10, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

                cv2.putText(frame, f"Total Delay: {total_delay_ms:.1f} ms", (10, 100),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                # Save the processed frame and count for the GUI to fetch
                self.latest_frame = frame
                self.weed_count = current_weed_count

        except Exception as e:
            print(f"Stream ended or error: {e}")
        finally:
            self.stop()

    def get_frame(self):
        """Called constantly by the Tkinter GUI to update the screen."""
        return self.latest_frame, self.weed_count

    def stop(self):
        """Safely shuts down the server and network thread."""
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
        print("Receiver stopped.")