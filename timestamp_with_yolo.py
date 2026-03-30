import cv2
import time
import socket
import pickle
import struct
import numpy as np
from ultralytics import YOLO  # <-- Added required import

# --- Configuration ---
HOST_IP = '0.0.0.0'  # Listen on all adapters
PORT = 8080  # Make sure this matches your Pi script!
MODEL_PATH = "dataPath/train/weights/best3.pt"  # Your model path

# --- 1. Load the YOLO Model ---
# We do this FIRST, before anything else, so it doesn't slow down the video feed.
print(f"Loading YOLO model from {MODEL_PATH}...")
try:
    model = YOLO(MODEL_PATH)
    print("✅ Model loaded successfully!")
except Exception as e:
    print(f"❌ Failed to load model: {e}")
    exit()  # Stop the script if the model isn't found

# --- 2. Setup Network Server ---
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# Prevent "Port in use" errors on crash
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server_socket.bind((HOST_IP, PORT))
server_socket.listen(1)
print(f"\nListening for Pi on port {PORT}...")

conn, addr = server_socket.accept()
print(f"Connected to Pi at {addr}")

data = b""
payload_size = struct.calcsize("Q")

try:
    while True:
        # 1. Receive the message size
        while len(data) < payload_size:
            packet = conn.recv(4 * 1024)
            if not packet: break
            data += packet
        if not data: break

        packed_msg_size = data[:payload_size]
        data = data[payload_size:]
        msg_size = struct.unpack("Q", packed_msg_size)[0]

        # 2. Receive the actual payload (timestamp + frame)
        while len(data) < msg_size:
            data += conn.recv(4 * 1024)

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

        results = model(frame)

        # Draw the bounding boxes onto the frame
        frame = results[0].plot()

        # ==========================================
        # MEASUREMENT 2: TOTAL DELAY
        # ==========================================
        finish_time = time.time()
        total_delay_ms = (finish_time - send_time) * 1000

        # Calculate just the YOLO processing time
        yolo_processing_ms = total_delay_ms - network_delay_ms

        # Print the stats to the terminal
        print(f"Net: {network_delay_ms:.1f}ms | YOLO: {yolo_processing_ms:.1f}ms | Total: {total_delay_ms:.1f}ms")

        # Overlay the stats on the video feed
        cv2.putText(frame, f"Net Delay: {network_delay_ms:.1f} ms", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 165, 0), 2)

        cv2.putText(frame, f"YOLO Time: {yolo_processing_ms:.1f} ms", (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        cv2.putText(frame, f"Total Delay: {total_delay_ms:.1f} ms", (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # Display the video
        cv2.imshow("Drone Feed", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"Stream ended or error: {e}")
finally:
    conn.close()
    server_socket.close()
    cv2.destroyAllWindows()