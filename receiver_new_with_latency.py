"""
Windows Laptop Receiver + YOLOv8 Plant Detection
Receives UDP MPEG-TS stream from Raspberry Pi and runs inference.
"""

import cv2
from ultralytics import YOLO
import sys
import time
import pytesseract
import re
import numpy as np


class Receiver:
    def __init__(self):
        # === CONFIG ===
        self.STREAM_URL = "udp://192.168.137.40:8000"  # Listen on port 8000
        self.MODEL_PATH = "C:/Users/BiLKANCOMPUTERS/Desktop/bitirme/best.pt"  # Model directory path
        self.model = None
        self.cap = None

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
        
        pytesseract.pytesseract.tesseract_cmd = (
        r"C:/Program Files/Tesseract-OCR/tesseract.exe"
        )


        # Regex for unix timestamp like: 1703965043.123
        TS_REGEX = re.compile(r"\d{10}\.\d{3}")

        

        roi = frame[20:80, 10:350]
                
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1]

        text = pytesseract.image_to_string(gray,config="--psm 7 -c tessedit_char_whitelist=0123456789.")
        
        match = TS_REGEX.search(text)

        if match:
            sent_ts = float(match.group())
            now = time.time()
            latency_ms = (now - sent_ts) * 1000
        else:
            latency_ms = 0

        

        # Run YOLO inference
        results = self.model(frame, verbose=False, device='cpu')
        annotated_frame = results[0].plot()  # Draw boxes & labels
        weed_count = len(results[0].boxes)

        

        return annotated_frame, weed_count, latency_ms

    def stop(self):
        # Cleanup
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        print("Stopped.")
