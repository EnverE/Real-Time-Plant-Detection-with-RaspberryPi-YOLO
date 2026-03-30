import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from datetime import datetime
import cv2
import threading
import time

from timestamp_with_yolo import Receiver


class WeedDetectionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Weed Detection Center")
        self.root.geometry("1000x600")
        self.root.configure(bg="#F4F6F9")
        self.working_time = None

        # Initializing logic code
        self.backend = Receiver()
        self.is_running = False
        self.entry_width = 0
        self.entry_length = 0

        # modern styling
        self.setup_styles()

        # Create Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Tab Frames
        self.tab_setup = ttk.Frame(self.notebook, style="Main.TFrame")
        self.tab_monitor = ttk.Frame(self.notebook, style="Main.TFrame")
        self.tab_stats = ttk.Frame(self.notebook, style="Main.TFrame")

        self.notebook.add(self.tab_setup, text="   Setup   ")
        self.notebook.add(self.tab_monitor, text="   Monitor   ")
        self.notebook.add(self.tab_stats, text="   Statistics   ")

        # Build Layouts for each tab
        self.build_setup_tab()
        self.build_monitor_tab()
        self.build_stats_tab()

    def setup_styles(self):
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')

        bg_color = "#F4F6F9"
        text_color = "#2C3E50"

        style.configure("Main.TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, foreground=text_color, font=("Segoe UI", 11))
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("TNotebook", background=bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 12, "bold"), padding=[15, 5])

    def build_setup_tab(self):
        # Center Container
        container = ttk.Frame(self.tab_setup, style="Main.TFrame")
        container.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(container, text="Area Setup", style="Header.TLabel").pack(pady=(0, 20))

        ttk.Label(container, text="Area Width (m)").pack(anchor="w")
        self.entry_width = ttk.Entry(container, font=("Segoe UI", 12), width=30)
        self.entry_width.pack(pady=(0, 15), ipady=5)

        ttk.Label(container, text="Area Length (m)").pack(anchor="w")
        self.entry_length = ttk.Entry(container, font=("Segoe UI", 12), width=30)
        self.entry_length.pack(pady=(0, 25), ipady=5)

        btn_save = tk.Button(container, text="Save Area", bg="#3498DB", fg="white",
                             font=("Segoe UI", 12, "bold"), relief="flat", command=self.save_setup,
                             activebackground="#2980B9", activeforeground="white")
        btn_save.pack(fill="x", ipady=5)

    def build_monitor_tab(self):
        # Left Panel
        left_panel = tk.Frame(self.tab_monitor, bg="#FFFFFF", bd=1, relief="ridge")
        left_panel.pack(side="left", fill="y", padx=(20, 10), pady=20)
        left_panel.config(width=280)
        left_panel.pack_propagate(False) # Maintains fixed width

        # right panel
        right_panel = tk.Frame(self.tab_monitor, bg="#F4F6F9")
        right_panel.pack(side="right", fill="both", expand=True, padx=(10, 20), pady=20)

        # Left panel content
        tk.Label(left_panel, text="Control Panel", font=("Segoe UI", 14, "bold"), bg="#FFFFFF", fg="#2C3E50").pack(pady=(20, 15))

        self.lbl_status = tk.Label(left_panel, text="Stream System: Idle", font=("Segoe UI", 11), bg="#FFFFFF", fg="#2C3E50")
        self.lbl_status.pack(pady=5, anchor="w", padx=20)

        tk.Label(left_panel, text="Spray System: Idle", font=("Segoe UI", 11), bg="#FFFFFF", fg="#2C3E50").pack(pady=5, anchor="w", padx=20)

        self.lbl_count = tk.Label(left_panel, text="Weeds in Frame: 0", font=("Segoe UI", 12, "bold"), bg="#FFFFFF", fg="#E74C3C")
        self.lbl_count.pack(pady=(15, 30), anchor="w", padx=20)

        self.btn_start = tk.Button(left_panel, text="Start Mission", bg="#2ECC71", fg="white",
                                   font=("Segoe UI", 12, "bold"), relief="flat",
                                   command=self.start_system, activebackground="#27AE60", activeforeground="white")
        self.btn_start.pack(fill="x", padx=20, pady=10, ipady=5)

        self.btn_stop = tk.Button(left_panel, text="Stop Mission", bg="#E74C3C", fg="white",
                                  font=("Segoe UI", 12, "bold"), relief="flat", state="disabled",
                                  command=self.stop_system, activebackground="#C0392B", activeforeground="white")
        self.btn_stop.pack(fill="x", padx=20, pady=10, ipady=5)

        video_frame = tk.Frame(right_panel, bg="black", bd=2, relief="flat")
        video_frame.pack(fill="both", expand=True)

        self.video_label = tk.Label(video_frame, text="[Live Video Feed]", bg="black", fg="white", font=("Segoe UI", 14))
        self.video_label.pack(fill="both", expand=True)

    def build_stats_tab(self):
        container = ttk.Frame(self.tab_stats, style="Main.TFrame")
        container.pack(fill="both", expand=True, padx=40, pady=40)

        top_frame = ttk.Frame(container, style="Main.TFrame")
        top_frame.pack(fill="x", expand=True)

        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(1, weight=1)
        top_frame.columnconfigure(2, weight=1)

        # 1. Mission Status
        col1 = ttk.Frame(top_frame, style="Main.TFrame")
        col1.grid(row=0, column=0, sticky="nw", padx=10)
        ttk.Label(col1, text="Mission Status:", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        self.lbl_width_stat = ttk.Label(col1, text="Area Width (m): 0")
        self.lbl_width_stat.pack(anchor="w", pady=2)

        self.lbl_length_stat = ttk.Label(col1, text="Area Length (m): 0")
        self.lbl_length_stat.pack(anchor="w", pady=2)

        self.lbl_time_stat = ttk.Label(col1, text="Time Elapsed: 00:00")
        self.lbl_time_stat.pack(anchor="w", pady=2)

        # 2. Detection Stats
        col2 = ttk.Frame(top_frame, style="Main.TFrame")
        col2.grid(row=0, column=1, sticky="nw", padx=10)
        ttk.Label(col2, text="Detection Stats:", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        self.lbl_crop_stat = ttk.Label(col2, text="Crops detected: 0")
        self.lbl_crop_stat.pack(anchor="w", pady=2)


        self.lbl_weed_stat = ttk.Label(col2, text="Weeds detected: 0")
        self.lbl_weed_stat.pack(anchor="w", pady=2)

        self.lbl_ratio_stat = ttk.Label(col2, text="Weed to crop ratio: %0")
        self.lbl_ratio_stat.pack(anchor="w", pady=10)

        # 3. Spraying Stats
        col3 = ttk.Frame(top_frame, style="Main.TFrame")
        col3.grid(row=0, column=2, sticky="nw", padx=10)
        ttk.Label(col3, text="Spraying Stats:", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        self.lbl_pump_stat = ttk.Label(col3, text="Pump activations: 0")
        self.lbl_pump_stat.pack(anchor="w", pady=2)

        self.lbl_estChem_stat = ttk.Label(col3, text="Estimated chemical used: 0L")
        self.lbl_estChem_stat.pack(anchor="w", pady=2)

        # Report Button
        btn_report = tk.Button(container, text="Create Report", bg="#34495E", fg="white",
                               font=("Segoe UI", 12, "bold"), relief="flat",
                               command=self.create_report,activebackground="#2C3E50", activeforeground="white")
        btn_report.pack(side="bottom", pady=40, ipadx=20, ipady=5)

    def save_setup(self):
        self.width = self.entry_width.get()
        self.length = self.entry_length.get()

        if not self.width or not self.length:
            messagebox.showerror("Error","Area can not be empty")
            return
        if int(self.width) <= 0 or int(self.length) <=0:
            messagebox.showerror("Error","Please enter a valid input")
            return

        self.lbl_width_stat.config(text=f"Area Width (m): {self.width}")
        self.lbl_length_stat.config(text=f"Area Length (m): {self.length}")
        messagebox.showinfo("Success","Area saved successfully")


    def create_report(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension = ".txt",
            filetypes=[("Text Files","*.txt"), ("All Files","*.*")],
            title ="Save Report"
        )
        if not filepath:
            return

        content = f"""
Statistics report for weed detection, generated at {datetime.now().strftime("%d-%m-%Y %H:%M")}
        
--- Mission Status ---
{self.lbl_width_stat.cget("text")}
{self.lbl_length_stat.cget("text")}
{self.lbl_time_stat.cget("text")}
        
--- Detection Stats ---
{self.lbl_crop_stat.cget("text")}
{self.lbl_weed_stat.cget("text")}
{self.lbl_ratio_stat.cget("text")}
        
--- Spray Status ---
{self.lbl_pump_stat.cget("text")}
{self.lbl_estChem_stat.cget("text")}
        
"""

        try:
            with open(filepath,"w") as file:
                file.write(content)
                messagebox.showinfo("Success",f"Report saved to {filepath}")
        except Exception as e:
            messagebox.showerror("Error",f"Failed to save report: {e}")



    def start_system(self):
        # connect to camera
        success = self.backend.initialize()
        if not success:
            self.lbl_status.config(text="Error! Connection failed")
            return

        self.is_running = True
        self.working_time = time.time()
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
        self.lbl_count.config(text=f"Detected in Frame: {count}")
        if self.working_time is not None:
            elapsed = int(time.time() - self.working_time)
            minutes, seconds = divmod(elapsed,60)
            live_time = f"{minutes:02d}:{seconds:02d}"
            self.lbl_time_stat.config(text=f"Time Elapsed: {live_time}")


if __name__ == "__main__":
    root = tk.Tk()
    app = WeedDetectionGUI(root)
    root.mainloop()