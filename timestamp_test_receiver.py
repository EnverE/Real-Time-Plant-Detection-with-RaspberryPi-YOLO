import cv2
import time
import socket
import pickle
import struct
import numpy as np

# --- Configuration ---
HOST_IP = '0.0.0.0'  # Listen on all adapters
PORT = 8080

# --- Setup Network Server ---
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST_IP, PORT))
server_socket.listen(1)
print(f"Listening for Pi on port {PORT}...")

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

        # 5. Calculate the delay!
        receive_time = time.time()
        delay_ms = (receive_time - send_time) * 1000

        # Print the delay to the terminal
        print(f"Total Delay: {delay_ms:.1f} ms")

        # Overlay the delay on the video feed
        cv2.putText(frame, f"Delay: {delay_ms:.1f} ms", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

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