"""
Windows Laptop Receiver + YOLOv8 Plant Detection
Receives UDP MPEG-TS stream from Raspberry Pi and runs inference.
"""

import cv2
from ultralytics import YOLO
import sys
from numba import jit, cuda


class Receiver:
    def __init__(self):
        # === CONFIG ===
        self.STREAM_URL = "udp://192.168.137.208:8000"  # Listen on port 8000
        self.MODEL_PATH = "dataPath/train/weights/best.pt"  # Model directory path
        self.model = None
        self.cap = None
        self.unique_ids = set()

    def initialize(self):
        # Load YOLO model
        try:
            self.model = YOLO(self.MODEL_PATH)
            print(f"Loaded model: {self.MODEL_PATH}")
        except Exception as e:
            print(f"!! Failed to load model: {e}")
            return False

        # Open video stream
        self.cap = cv2.VideoCapture(self.STREAM_URL, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduced buffer for lower latency

        if not self.cap.isOpened():
            print("!! Could not open UDP stream. Is the Pi streaming?")
            return False

        print("Receiving stream... Press 'q' to quit.")
        return True # successfully initialized

    def get_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            print("!!! No frame received. Stream may have ended.")
            return None, 0

        # Run YOLO inference
        results = self.model.track(frame, verbose=False, device='cpu', persist=True, tracker="bytetrack.yaml")
        annotated_frame = results[0].plot()  # Draw boxes & labels
        weed_count = len(results[0].boxes)
        
        if results[0].boxes.id is not None:
            track_ids = results[0].boxes.id.int().cpu().tolist()
            
            for object_id in track_ids:
                self.unique_ids.add(object_id)

        return annotated_frame, weed_count, len(self.unique_ids)

    def stop(self):
        # Cleanup
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        print("Stopped.")