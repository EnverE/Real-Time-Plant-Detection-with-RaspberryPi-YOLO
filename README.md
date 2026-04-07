🌱 Smart Weed Detection & Spraying System (Graduation Project)
📌 Overview

This project presents a Raspberry Pi–based smart agricultural system designed to detect unwanted weeds in real-time and trigger a spraying mechanism. The system uses live video streaming from a Raspberry Pi camera, processes the video on a laptop using a deep learning model, and performs actions based on detection results.

The goal of this project is to create a low-cost, efficient, and scalable solution for precision agriculture.

⚙️ System Architecture

The system consists of three main components:

Raspberry Pi 3 (Edge Device)
Captures live video using the Pi Camera and streams it over Wi-Fi.
Laptop (Processing Unit)
Receives the video stream and performs weed detection using a YOLOv8 model.
Control & Action Layer
Based on detection results, the system can trigger actions such as spraying.
🔧 Technologies Used
Hardware
Raspberry Pi 3 Model B
Raspberry Pi Camera Module
Wi-Fi Network
Software
Python
rpicam-vid (video streaming)
FFmpeg (video decoding)
OpenCV
YOLOv8 (object detection)
Flask (backend communication)
Tkinter (GUI)
🚀 Features
📡 Real-time video streaming over Wi-Fi
🧠 AI-based weed detection using YOLOv8
⚡ Low-latency communication between Pi and laptop
📊 Performance evaluation (latency, CPU usage, packet loss)
🖥️ Simple GUI for system control and monitoring
🧪 Evaluation Summary

The system was tested under controlled Wi-Fi conditions. Key observations:

Latency: ~100 ms (end-to-end)
CPU Usage (Pi): ~27.8% during streaming
Performance: Stable streaming with minor frame drops

These results show that the system works reliably for real-time monitoring, with trade-offs between latency and processing complexity.

⚠️ Limitations
Tested only under ideal Wi-Fi conditions
Latency affected by CPU-based inference
Packet loss due to UDP transmission
No outdoor/field testing yet
👥 Team
Enver Eren Tatlidil
Emir Canli
Efe Soylemis
Burak Mirac Dumlu
📄 License

This project is for academic purposes.
