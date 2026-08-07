import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from datetime import datetime
import cv2
import threading
import time

import config
from receiver import Receiver
from pi_connector import PiConnector

class WeedDetectionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ESC-492 Drone Weed Detection Center")
        self.root.geometry("1100x680")
        self.root.configure(bg="#094218")
        self.root.resizable(True, True)

        self.cfg = config.load_config()
        self.pi = PiConnector(self.cfg)
        self.backend = Receiver(self.cfg)

        self.is_running = False
        self.working_time = None

        self.setup_styles()
        self.build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.backend.model is None:
            self.lbl_status.config(text="Model not loaded", fg="#EF4444")
            messagebox.showerror("Model not loaded", self.backend.model_error)

    # ------------------------------------------------------------------ styles
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        BG     = "#094218"
        CARD   = "#1A1D27"
        BORDER = "#2A2D3A"
        TEXT   = "#E8EAF0"
        MUTED  = "#6B7280"

        style.configure("Main.TFrame",   background=BG)
        style.configure("Card.TFrame",   background=CARD)
        style.configure("TLabel",        background=CARD, foreground=TEXT,  font=("Segoe UI", 11))
        style.configure("Muted.TLabel",  background=CARD, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=CARD, foreground=TEXT,  font=("Segoe UI", 13, "bold"))
        style.configure("BG.TLabel",     background=BG,   foreground=TEXT,  font=("Segoe UI", 11))
        style.configure("TNotebook",        background=BG,   borderwidth=0)
        style.configure("TNotebook.Tab",    background=CARD, foreground=MUTED,
                        font=("Segoe UI", 11, "bold"), padding=[18, 8])
        style.map("TNotebook.Tab",
                  background=[("selected", "#1E2235")],
                  foreground=[("selected", TEXT)])
        style.configure("TScale", background=CARD, troughcolor="#2A2D3A",
                        sliderlength=14, sliderrelief="flat")

    # ------------------------------------------------------------------ layout
    def build_layout(self):
        # Top bar
        topbar = tk.Frame(self.root, bg="#13151F", height=46)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="ESC-492 Drone", bg="#13151F", fg="#E8EAF0",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=18, pady=12)

        self.lbl_topstatus = tk.Label(topbar, text="● Idle", bg="#13151F",
                                      fg="#6B7280", font=("Segoe UI", 11))
        self.lbl_topstatus.pack(side="left", padx=6)

        self.lbl_elapsed = tk.Label(topbar, text="00:00:00", bg="#13151F",
                                    fg="#6B7280", font=("Segoe UI", 11, "bold"))
        self.lbl_elapsed.pack(side="right", padx=18)

        self.lbl_pixhawk = tk.Label(topbar, text="Pixhawk: not connected",
                                    bg="#13151F", fg="#F59E0B", font=("Segoe UI", 10))
        self.lbl_pixhawk.pack(side="right", padx=12)

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)

        self.tab_monitor = ttk.Frame(self.notebook, style="Main.TFrame")
        self.tab_setup   = ttk.Frame(self.notebook, style="Main.TFrame")
        self.tab_stats   = ttk.Frame(self.notebook, style="Main.TFrame")

        self.notebook.add(self.tab_monitor, text="  Monitor  ")
        self.notebook.add(self.tab_setup,   text="  Setup  ")
        self.notebook.add(self.tab_stats,   text="  Statistics  ")

        self.build_monitor_tab()
        self.build_setup_tab()
        self.build_stats_tab()

    # ------------------------------------------------------------------ monitor
    def build_monitor_tab(self):
        outer = tk.Frame(self.tab_monitor, bg="#094218")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        # Left sidebar
        sidebar = tk.Frame(outer, bg="#094218", width=240)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)

        self._build_control_card(sidebar)
        self._build_pump_card(sidebar)
        self._build_live_stats_card(sidebar)

        # Right: video + metrics
        right = tk.Frame(outer, bg="#094218")
        right.pack(side="right", fill="both", expand=True)

        # Metrics row — packed FIRST so video can't push it out
        metrics = tk.Frame(right, bg="#094218")
        metrics.pack(side="bottom", fill="x", pady=(8, 0))

        # Video — fills remaining space only
        video_wrap = tk.Frame(right, bg="#000000", bd=0)
        video_wrap.pack(side="top", fill="both", expand=True)

        self.video_label = tk.Label(video_wrap, text="Waiting for stream...",
                                    bg="#0A0A0F", fg="#2A2D3A",
                                    font=("Segoe UI", 14))
        self.video_label.imgtk = None       # holds a reference to the live frame
        self.video_label.pack(fill="both", expand=True)

        self.metric_vars = {}
        metric_defs = [
            ("Net delay", "network_delay_ms", "ms"),
            ("YOLO time", "yolo_ms", "ms"),
            ("Live FPS", "fps", "fps"),
            ("Pump", "pump_state", ""),
        ]
        for label, key, unit in metric_defs:
            card = tk.Frame(metrics, bg="#1A1D27", bd=0)
            card.pack(side="left", fill="x", expand=True, padx=(0, 6))
            tk.Label(card, text=label, bg="#1A1D27", fg="#6B7280",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(8, 0))
            var = tk.StringVar(value="—")
            self.metric_vars[key] = var
            row = tk.Frame(card, bg="#1A1D27")
            row.pack(anchor="w", padx=10, pady=(0, 8))
            tk.Label(row, textvariable=var, bg="#1A1D27", fg="#E8EAF0",
                     font=("Segoe UI", 18, "bold")).pack(side="left")
            if unit:
                tk.Label(row, text=f" {unit}", bg="#1A1D27", fg="#6B7280",
                         font=("Segoe UI", 10)).pack(side="left", pady=(6, 0))

    def _card(self, parent, title):
        wrap = tk.Frame(parent, bg="#1A1D27", bd=0)
        wrap.pack(fill="x", pady=(0, 8))
        tk.Label(wrap, text=title.upper(), bg="#1A1D27", fg="#4B5563",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        return wrap

    def _build_control_card(self, parent):
        card = self._card(parent, "Mission control")

        self.lbl_status = tk.Label(card, text="Status: Idle", bg="#1A1D27",
                                   fg="#6B7280", font=("Segoe UI", 11))
        self.lbl_status.pack(anchor="w", padx=12, pady=(0, 8))

        self.btn_start = tk.Button(card, text="Start mission",
                                   bg="#16A34A", fg="white", activebackground="#15803D",
                                   activeforeground="white",
                                   font=("Segoe UI", 11, "bold"), relief="flat",
                                   bd=0, cursor="hand2", command=self.start_system)
        self.btn_start.pack(fill="x", padx=12, pady=(0, 4), ipady=6)

        self.btn_stop = tk.Button(card, text="Stop mission",
                                  bg="#2A2D3A", fg="#9CA3AF", activebackground="#374151",
                                  activeforeground="white",
                                  font=("Segoe UI", 11, "bold"), relief="flat",
                                  bd=0, state="disabled", cursor="hand2",
                                  command=self.stop_system)
        self.btn_stop.pack(fill="x", padx=12, pady=(0, 10), ipady=6)

    def _build_pump_card(self, parent):
        card = self._card(parent, "Pump control")

        # Pump indicator
        ind_row = tk.Frame(card, bg="#1A1D27")
        ind_row.pack(fill="x", padx=12, pady=(0, 8))

        self.pump_dot = tk.Label(ind_row, text="●", bg="#1A1D27",
                                 fg="#374151", font=("Segoe UI", 14))
        self.pump_dot.pack(side="left")
        self.pump_lbl = tk.Label(ind_row, text="  Pump: off", bg="#1A1D27",
                                 fg="#6B7280", font=("Segoe UI", 11, "bold"))
        self.pump_lbl.pack(side="left")

        # Mode toggle
        mode_row = tk.Frame(card, bg="#1A1D27")
        mode_row.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(mode_row, text="Mode", bg="#1A1D27", fg="#6B7280",
                 font=("Segoe UI", 10)).pack(side="left")

        self.pump_mode_var = tk.StringVar(value=self.cfg["pump"]["mode"])
        for val, txt in [("auto", "Auto"), ("manual", "Manual")]:
            tk.Radiobutton(mode_row, text=txt, variable=self.pump_mode_var,
                           value=val, bg="#1A1D27", fg="#9CA3AF",
                           selectcolor="#094218", activebackground="#1A1D27",
                           font=("Segoe UI", 10), cursor="hand2",
                           command=self._on_mode_change).pack(side="right", padx=4)

        # Threshold slider (auto mode)
        self.threshold_frame = tk.Frame(card, bg="#1A1D27")
        self.threshold_frame.pack(fill="x", padx=12, pady=(0, 6))

        thresh_top = tk.Frame(self.threshold_frame, bg="#1A1D27")
        thresh_top.pack(fill="x")
        tk.Label(thresh_top, text="Min detections to spray",
                 bg="#1A1D27", fg="#6B7280", font=("Segoe UI", 10)).pack(side="left")
        self.lbl_threshold = tk.Label(thresh_top, text=str(self.backend.spray_threshold),
                                      bg="#1A1D27", fg="#E8EAF0",
                                      font=("Segoe UI", 10, "bold"))
        self.lbl_threshold.pack(side="right")

        self.threshold_slider = tk.Scale(self.threshold_frame, from_=1, to=10,
                                         orient="horizontal", bg="#1A1D27",
                                         fg="#6B7280", troughcolor="#2A2D3A",
                                         highlightthickness=0, bd=0,
                                         showvalue=False, cursor="hand2",
                                         command=self._on_threshold_change)
        self.threshold_slider.set(self.backend.spray_threshold)
        self.threshold_slider.pack(fill="x", pady=(2, 0))

        # Manual spray button
        self.btn_spray = tk.Button(card, text="Fire pump manually",
                                   bg="#B45309", fg="white",
                                   activebackground="#92400E", activeforeground="white",
                                   font=("Segoe UI", 10, "bold"), relief="flat",
                                   bd=0, cursor="hand2", state="disabled",
                                   command=self._manual_spray)
        self.btn_spray.pack(fill="x", padx=12, pady=(0, 4), ipady=5)

        # Pixhawk note
        tk.Label(card, text="Pixhawk: mock mode", bg="#1A1D27",
                 fg="#4B5563", font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(0, 10))

    def _build_live_stats_card(self, parent):
        card = self._card(parent, "Live detections")

        rows = [
            ("Weeds in frame", "lbl_live_weeds",  "0",   "#EF4444"),
            ("Total weeds",    "lbl_total_weeds",  "0",   "#E8EAF0"),
            ("Spray triggers", "lbl_sprays",       "0",   "#F59E0B"),
        ]
        for label, attr, default, color in rows:
            row = tk.Frame(card, bg="#1A1D27")
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=label, bg="#1A1D27", fg="#6B7280",
                     font=("Segoe UI", 10)).pack(side="left")
            lbl = tk.Label(row, text=default, bg="#1A1D27", fg=color,
                           font=("Segoe UI", 10, "bold"))
            lbl.pack(side="right")
            setattr(self, attr, lbl)

        # Padding
        tk.Frame(card, bg="#1A1D27", height=8).pack()

    # ------------------------------------------------------------------ setup tab
    def build_setup_tab(self):
        outer = tk.Frame(self.tab_setup, bg="#094218")
        outer.pack(fill="both", expand=True)

        container = tk.Frame(outer, bg="#1A1D27", bd=0)
        container.place(relx=0.5, rely=0.45, anchor="center", width=380)

        tk.Label(container, text="Area setup", bg="#1A1D27", fg="#E8EAF0",
                 font=("Segoe UI", 15, "bold")).pack(pady=(24, 16), padx=24, anchor="w")

        for label, attr in [("Area width (m)", "entry_width"),
                             ("Area length (m)", "entry_length")]:
            tk.Label(container, text=label, bg="#1A1D27", fg="#9CA3AF",
                     font=("Segoe UI", 10)).pack(anchor="w", padx=24)
            entry = tk.Entry(container, bg="#094218", fg="#E8EAF0",
                             insertbackground="#E8EAF0", relief="flat",
                             font=("Segoe UI", 12), bd=0)
            entry.pack(fill="x", padx=24, pady=(4, 14), ipady=8)
            setattr(self, attr, entry)

        # Pump duration
        tk.Label(container, text="Pump on-duration (seconds)", bg="#1A1D27",
                 fg="#9CA3AF", font=("Segoe UI", 10)).pack(anchor="w", padx=24)

        dur_row = tk.Frame(container, bg="#1A1D27")
        dur_row.pack(fill="x", padx=24, pady=(4, 20))
        self.lbl_duration = tk.Label(dur_row, text="2.0 s", bg="#1A1D27",
                                     fg="#E8EAF0", font=("Segoe UI", 11, "bold"))
        self.lbl_duration.pack(side="right")
        self.duration_slider = tk.Scale(dur_row, from_=0.5, to=10.0,
                                        resolution=0.5, orient="horizontal",
                                        bg="#1A1D27", fg="#6B7280",
                                        troughcolor="#2A2D3A", highlightthickness=0,
                                        bd=0, showvalue=False, cursor="hand2",
                                        command=self._on_duration_change)
        self.duration_slider.set(self.backend.pump_duration)
        self.lbl_duration.config(text=f"{self.backend.pump_duration:.1f} s")
        self.duration_slider.pack(side="left", fill="x", expand=True)

        tk.Button(container, text="Save settings", bg="#2563EB", fg="white",
                  activebackground="#1D4ED8", activeforeground="white",
                  font=("Segoe UI", 11, "bold"), relief="flat", bd=0,
                  cursor="hand2", command=self.save_setup).pack(
                  fill="x", padx=24, pady=(0, 24), ipady=8)

    # ------------------------------------------------------------------ stats tab
    def build_stats_tab(self):
        outer = tk.Frame(self.tab_stats, bg="#094218")
        outer.pack(fill="both", expand=True, padx=20, pady=20)

        # Three columns
        cols_frame = tk.Frame(outer, bg="#094218")
        cols_frame.pack(fill="x")

        def col(title):
            f = tk.Frame(cols_frame, bg="#1A1D27", bd=0)
            f.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Label(f, text=title, bg="#1A1D27", fg="#4B5563",
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
            return f

        def stat_row(parent, label, attr, default="—", color="#E8EAF0"):
            row = tk.Frame(parent, bg="#1A1D27")
            row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=label, bg="#1A1D27", fg="#6B7280",
                     font=("Segoe UI", 10)).pack(side="left")
            lbl = tk.Label(row, text=default, bg="#1A1D27", fg=color,
                           font=("Segoe UI", 10, "bold"))
            lbl.pack(side="right")
            setattr(self, attr, lbl)

        c1 = col("Mission status")
        stat_row(c1, "Area width",    "stat_width")
        stat_row(c1, "Area length",   "stat_length")
        stat_row(c1, "Time elapsed",  "stat_time")
        stat_row(c1, "Pump mode",     "stat_pump_mode")
        tk.Frame(c1, bg="#1A1D27", height=12).pack()

        c2 = col("Detection stats")
        stat_row(c2, "Total weeds",   "stat_weeds",  "0", "#EF4444")
        stat_row(c2, "Total crops",   "stat_crops",  "0", "#22C55E")
        stat_row(c2, "Weed ratio",    "stat_ratio",  "0%", "#F59E0B")
        tk.Frame(c2, bg="#1A1D27", height=12).pack()

        c3 = col("Spray stats")
        stat_row(c3, "Activations",   "stat_sprays", "0")
        stat_row(c3, "Est. chem used","stat_chem",   "0.0 L")
        stat_row(c3, "Pump duration", "stat_dur",    f"{self.backend.pump_duration:.1f} s")
        tk.Frame(c3, bg="#1A1D27", height=12).pack()

        # Report button
        tk.Button(outer, text="Save report", bg="#374151", fg="#E8EAF0",
                  activebackground="#4B5563", activeforeground="white",
                  font=("Segoe UI", 11, "bold"), relief="flat", bd=0,
                  cursor="hand2", command=self.create_report).pack(
                  side="bottom", pady=20, ipadx=24, ipady=7)

    # ------------------------------------------------------------------ actions
    def start_system(self):
        if self.backend.model is None:
            messagebox.showerror("Model not loaded", self.backend.model_error)
            return
        self.lbl_status.config(text="Starting receiver...", fg="#F59E0B")
        self.btn_start.config(state="disabled")
        self.root.update()
        threading.Thread(target=self._connect_and_start, daemon=True).start()

    def _connect_and_start(self):
        # Step 1 — start listening first, so the Pi has somewhere to connect to
        if not self.backend.initialize():
            self.root.after(0, self._on_start_failed,
                            f"Receiver failed to bind port {self.backend.PORT}.")
            return

        # Step 2 — SSH into the Pi and launch the sender
        if not self.pi.connect_and_start():
            self.backend.stop()
            self.root.after(0, self._on_start_failed,
                            self.pi.last_error or "Could not reach the Pi over SSH.")
            return

        self.root.after(0, self._on_start_success)

    def _on_start_success(self):
        self.is_running = True
        self.working_time = time.time()
        self.btn_stop.config(state="normal", bg="#DC2626", fg="white")
        self.btn_start.config(bg="#374151", fg="#6B7280")
        self.lbl_status.config(text="Status: Live", fg="#22C55E")
        self.lbl_topstatus.config(text="● Live", fg="#22C55E")
        if self.pump_mode_var.get() == "manual":
            self.btn_spray.config(state="normal")
        threading.Thread(target=self.video_loop, daemon=True).start()
        self._tick_elapsed()

    def _on_start_failed(self, reason):
        self.lbl_status.config(text="Status: Failed", fg="#EF4444")
        self.btn_start.config(state="normal", bg="#16A34A", fg="white")
        messagebox.showerror("Could not start the mission", reason)

    def stop_system(self):
        self.is_running = False
        self.backend.stop()
        self.pi.stop_sender()
        self.btn_start.config(state="normal", bg="#16A34A", fg="white")
        self.btn_stop.config(state="disabled", bg="#2A2D3A", fg="#9CA3AF")
        self.btn_spray.config(state="disabled")
        self.lbl_topstatus.config(text="● Idle", fg="#6B7280")
        self.video_label.config(image="", text="Stream stopped")
        self.video_label.imgtk = None

        stopped = "Status: Stopped"
        if self.backend.log_path:
            stopped += f" — log: {self.backend.log_path.name}"
        self.lbl_status.config(text=stopped, fg="#6B7280")

    def on_close(self):
        """Stop the Pi sender before the window disappears."""
        if self.is_running:
            self.stop_system()
        self.root.destroy()

    def save_setup(self):
        w = self.entry_width.get().strip().replace(",", ".")
        l = self.entry_length.get().strip().replace(",", ".")
        if not w or not l:
            messagebox.showerror("Error", "Width and length cannot be empty.")
            return
        try:
            if float(w) <= 0 or float(l) <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Please enter valid positive numbers.")
            return

        self.stat_width.config(text=f"{float(w):g} m")
        self.stat_length.config(text=f"{float(l):g} m")
        messagebox.showinfo("Saved", "Settings saved successfully.")

    def _on_mode_change(self):
        mode = self.pump_mode_var.get()
        self.backend.set_pump_mode(mode)
        if mode == "manual":
            self.btn_spray.config(state="normal" if self.is_running else "disabled")
            self.threshold_frame.pack_forget()
        else:
            self.btn_spray.config(state="disabled")
            self.threshold_frame.pack(fill="x", padx=12, pady=(0, 6),
                                      before=self.btn_spray)

    def _on_threshold_change(self, val):
        v = int(float(val))
        self.lbl_threshold.config(text=str(v))
        self.backend.set_spray_threshold(v)

    def _on_duration_change(self, val):
        v = float(val)
        self.lbl_duration.config(text=f"{v:.1f} s")
        self.backend.pump_duration = v
        self.stat_dur.config(text=f"{v:.1f} s")

    def _manual_spray(self):
        if self.is_running:
            self.backend.trigger_pump_manual()

    def _tick_elapsed(self):
        if not self.is_running:
            return
        elapsed = int(time.time() - self.working_time)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        self.lbl_elapsed.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.stat_time.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.root.after(1000, self._tick_elapsed)

    # ------------------------------------------------------------------ video loop
    def video_loop(self):
        """Worker thread: decode + scale frames, then hand them to the UI thread.

        Only Tkinter calls belong on the main thread, so the PhotoImage itself is
        built in update_interface — creating it here would corrupt Tk's state.
        """
        last_frame = None
        while self.is_running:
            frame, _ = self.backend.get_frame()
            stats = self.backend.get_stats()

            if not self.backend.is_running:
                self.root.after(0, self._on_backend_died)
                return

            if frame is None or frame is last_frame:
                self.root.after(0, self.update_interface, None, stats)
                time.sleep(0.05)
                continue

            last_frame = frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Fit frame to video label size
            lw = self.video_label.winfo_width()
            lh = self.video_label.winfo_height()
            if lw > 10 and lh > 10:
                fh, fw = rgb.shape[:2]
                scale = min(lw / fw, lh / fh)
                rgb = cv2.resize(rgb, (int(fw * scale), int(fh * scale)))

            self.root.after(0, self.update_interface, Image.fromarray(rgb), stats)
            time.sleep(0.01)

    def _on_backend_died(self):
        if self.is_running:
            self.stop_system()
            messagebox.showwarning(
                "Stream lost",
                "The receiver stopped. Check the terminal output and the Pi's "
                "sender log for the reason.")

    def update_interface(self, img, stats):
        # Video
        if img is not None:
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk          # keep a reference alive
            self.video_label.configure(image=imgtk, text="")
        elif self.video_label.imgtk is None:
            waiting = {
                "waiting": "Waiting for the Pi to connect...",
                "connected": "Connected — waiting for frames...",
            }.get(stats["connection_state"], "Waiting for stream...")
            self.video_label.configure(text=waiting)

        # Metric cards
        self.metric_vars["network_delay_ms"].set(f"{stats['network_delay_ms']:.0f}")
        self.metric_vars["yolo_ms"].set(f"{stats['yolo_ms']:.0f}")
        self.metric_vars["fps"].set(f"{stats['fps']:.1f}")

        # Pump state
        pump_on = stats["pump_active"]
        if pump_on:
            self.pump_dot.config(fg="#22C55E")
            self.pump_lbl.config(text="  Pump: spraying", fg="#22C55E")
            self.metric_vars["pump_state"].set("ON")
        else:
            self.pump_dot.config(fg="#374151")
            self.pump_lbl.config(text="  Pump: off", fg="#6B7280")
            self.metric_vars["pump_state"].set("off")

        # Live stats sidebar
        self.lbl_live_weeds.config(text=str(stats["weed_count"]))
        self.lbl_total_weeds.config(text=str(stats["total_weeds"]))
        self.lbl_sprays.config(text=str(stats["spray_activations"]))

        # Stats tab
        tw = stats["total_weeds"]
        tc = stats["total_crops"]
        ratio = f"{(tw / (tw + tc) * 100):.1f}%" if (tw + tc) > 0 else "0%"
        self.stat_weeds.config(text=str(tw))
        self.stat_crops.config(text=str(tc))
        self.stat_ratio.config(text=ratio)
        self.stat_sprays.config(text=str(stats["spray_activations"]))
        self.stat_chem.config(text=f"{self._chem_used(stats):.2f} L")
        self.stat_pump_mode.config(text=stats["pump_mode"].capitalize())

    def _chem_used(self, stats):
        """Rough chemical estimate: litres per activation x activations."""
        return stats["spray_activations"] * self.cfg["pump"]["litres_per_activation"]

    # ------------------------------------------------------------------ report
    def create_report(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            title="Save Report"
        )
        if not filepath:
            return

        stats = self.backend.get_stats()
        tw = stats["total_weeds"]
        tc = stats["total_crops"]
        ratio = f"{(tw / (tw + tc) * 100):.1f}%" if (tw + tc) > 0 else "0%"

        content = f"""AgriDrone - Weed Detection Report
Generated: {datetime.now().strftime("%d-%m-%Y %H:%M")}

--- Mission Status ---
Area width:      {self.stat_width.cget("text")}
Area length:     {self.stat_length.cget("text")}
Time elapsed:    {self.stat_time.cget("text")}
Pump mode:       {stats["pump_mode"].capitalize()}

--- Detection Stats ---
Total weeds:     {tw}
Total crops:     {tc}
Weed ratio:      {ratio}

--- Spray Stats ---
Pump activations:       {stats["spray_activations"]}
Estimated chemical:     {self._chem_used(stats):.2f} L
Pump on-duration:       {self.backend.pump_duration:.1f} s

--- Link Quality ---
Frames received:        {stats["frames_received"]}
Frames dropped:         {stats["frames_dropped"]} ({stats["packet_loss_pct"]:.2f}%)
Network delay avg:      {stats["net_avg"]:.1f} ms (min {stats["net_min"]:.1f} / max {stats["net_max"]:.1f})
YOLO inference avg:     {stats["yolo_avg"]:.1f} ms
FPS avg:                {stats["fps_avg"]:.1f}
"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Report saved to {filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = WeedDetectionGUI(root)
    root.mainloop()
