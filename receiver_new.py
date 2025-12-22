"""
Windows Laptop Receiver + YOLOv8 Plant Detection
Receives UDP MPEG-TS stream from Raspberry Pi and runs inference.
"""

import cv2
from ultralytics import YOLO
import sys

# === CONFIG ===
STREAM_URL = "udp://192.168.137.208:8000"  # Listen on port 8000
MODEL_PATH = "dataPath/train/weights/best.pt"  # Model directory path

# Load YOLO model
try:
    model = YOLO(MODEL_PATH)
    print(f"Loaded model: {MODEL_PATH}")
except Exception as e:
    print(f"!! Failed to load model: {e}")
    sys.exit(1)

# Open video stream
cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduced buffer for lower latency

if not cap.isOpened():
    print("!! Could not open UDP stream. Is the Pi streaming?")
    sys.exit(1)

print("Receiving stream... Press 'q' to quit.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("!!! No frame received. Stream may have ended.")
            break

        # Run YOLO inference
        results = model(frame, verbose=False, device='cpu')
        annotated_frame = results[0].plot()  # Draw boxes & labels

        # Display result
        cv2.imshow("Plant Detection", annotated_frame)

        # Exit on 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    pass

# Cleanup
cap.release()
cv2.destroyAllWindows()
print("Stopped.")