
import tkinter as tk
from PIL import Image, ImageTk
import cv2
import threading
import time

from receiver_new import Receiver


class WeedDetectionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Weed Detection Center")
        self.root.geometry("1000x600")

        # Initializing logic code
        self.backend = Receiver()
        self.is_running = False

        # GUI LAYOUT
        # 1. Video Area
        self.video_label = tk.Label(root, text="[Video Feed Offline]", bg="black", fg="white")
        self.video_label.place(x=20, y=20, width=640, height=480)

        # 2. Statistics Area
        self.stats_frame = tk.Frame(root, bd=2, relief="groove", bg="#f0f0f0")
        self.stats_frame.place(x=680, y=20, width=280, height=480)

        tk.Label(self.stats_frame, text="LIVE STATS", font=("Arial", 16, "bold"), bg="#f0f0f0").pack(pady=10)

        self.lbl_status = tk.Label(self.stats_frame, text="Status: Idle", font=("Arial", 12), fg="blue", bg="#f0f0f0")
        self.lbl_status.pack(pady=5)

        self.lbl_count = tk.Label(self.stats_frame, text="Weeds in Frame: 0", font=("Arial", 14), bg="#f0f0f0")
        self.lbl_count.pack(pady=20)

        self.lbl_total = tk.Label(self.stats_frame, text="Total Detections: 0", font=("Arial", 12), fg="gray", bg="#f0f0f0")
        self.lbl_total.pack(pady=5)
        self.total_counter = 0

        # 3. Buttons
        self.btn_start = tk.Button(root, text="Start System", bg="green", fg="white", font=("Arial", 14), command=self.start_system)
        self.btn_start.place(x=20, y=520, width=200, height=50)

        self.btn_stop = tk.Button(root, text="Stop", bg="red", fg="white", font=("Arial", 14), command=self.stop_system, state="disabled")
        self.btn_stop.place(x=240, y=520, width=200, height=50)


    def start_system(self):
        # connect to camera
        success = self.backend.initialize()
        if not success:
            self.lbl_status.config(text="Error! Connection failed")
            return

        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.lbl_status.config(text="Status: Live", fg="green")

        # Start loop in background
        threading.Thread(target=self.video_loop, daemon=True).start()

    def stop_system(self):
        self.is_running = False
        self.backend.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_status.config(text="Status: Stopped", fg="black")

    def video_loop(self):
        while self.is_running:
            # Getting footage
            frame, count = self.backend.get_frame()

            if frame is not None:
                # Update Stats (DOES NOT WORK AS INTENDED - need a fix)
                self.total_counter += count

                # Update GUI Images
                # Convert BGR (OpenCV) to RGB (Tkinter)
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)

                # Send update to main thread
                self.root.after(0, self.update_interface, imgtk, count)
            else:
                # If stream fails temporarily
                time.sleep(0.1)

    def update_interface(self, imgtk, count):
        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)
        self.lbl_count.config(text=f"Weeds in Frame: {count}")
        self.lbl_total.config(text=f"Total Detections: {self.total_counter}")


if __name__ == "__main__":
    root = tk.Tk()
    app = WeedDetectionGUI(root)
    root.mainloop()