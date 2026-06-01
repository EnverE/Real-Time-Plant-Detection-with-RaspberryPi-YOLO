import cv2
import socket
import struct
import pickle
import time


def start_fake_camera():
    HOST_IP = '127.0.0.1'  # Sending to your own laptop
    PORT = 8080

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    print("Looking for GUI Receiver (Click 'Start Mission' in the GUI)...")
    while True:
        try:
            # Try to connect until the GUI opens the port
            client_socket.connect((HOST_IP, PORT))
            print("Connected to GUI!")
            break
        except:
            time.sleep(1)

    cap = cv2.VideoCapture(0)  # 0 is your laptop's built-in webcam
    frame_number = 0

    print("Streaming webcam to GUI. Show it a picture of a weed on your phone!")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # The real Pi encodes the frame to save bandwidth
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])

            # The Receiver expects a tuple of (frame_number, encoded_frame)
            payload = pickle.dumps((frame_number, buffer))
            message = struct.pack("Q", len(payload)) + payload

            client_socket.sendall(message)
            frame_number += 1

            time.sleep(0.05)  # Simulate ~20 FPS so your laptop doesn't melt
    except Exception as e:
        print(f"Stream stopped: {e}")
    finally:
        cap.release()
        client_socket.close()


if __name__ == "__main__":
    start_fake_camera()