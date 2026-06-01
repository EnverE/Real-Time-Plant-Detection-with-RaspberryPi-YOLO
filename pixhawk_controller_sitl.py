"""
Drop-in replacement for pixhawk_controller.py that connects to SITL
instead of real hardware. Use this for testing on your laptop.
"""

from pymavlink import mavutil
import time
import threading


class PixhawkController:
    def __init__(self, port='tcp:127.0.0.1:5760', baud=57600):
        self.port = port
        self.baud = baud
        self.master = None
        self.connected = False
        self._gps = None
        self._gps_lock = threading.Lock()

    def connect(self):
        try:
            print(f"[PIXHAWK-SITL] Connecting to {self.port}...")
            self.master = mavutil.mavlink_connection(self.port)
            print("[PIXHAWK-SITL] Waiting for heartbeat...")
            self.master.wait_heartbeat(timeout=10)
            self.connected = True
            print(f"[PIXHAWK-SITL] Connected! System ID: {self.master.target_system}")

            # Request data streams — SITL doesn't send them by default
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                10, 1
            )

            threading.Thread(target=self._gps_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"[PIXHAWK-SITL] Connection failed: {e}")
            self.connected = False
            return False

    def _gps_loop(self):
        while self.connected:
            try:
                msg = self.master.recv_match(
                    type='GLOBAL_POSITION_INT',
                    blocking=True,
                    timeout=2.0
                )
                if msg:
                    with self._gps_lock:
                        self._gps = {
                            "lat": msg.lat / 1e7,
                            "lon": msg.lon / 1e7,
                            "alt": msg.relative_alt / 1000.0
                        }
            except:
                time.sleep(0.5)

    def get_gps(self):
        with self._gps_lock:
            return self._gps.copy() if self._gps else None

    def has_gps_fix(self):
        with self._gps_lock:
            return self._gps is not None

    def trigger_pump(self, relay_pin=0, duration=2.0):
        if not self.connected:
            print("[PUMP-SITL] Not connected.")
            return
        print(f"[PUMP-SITL] Relay {relay_pin} ON")
        self._set_relay(relay_pin, 1)
        time.sleep(duration)
        self._set_relay(relay_pin, 0)
        print(f"[PUMP-SITL] Relay {relay_pin} OFF")

    def _set_relay(self, relay_pin, state):
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_RELAY,
            0, relay_pin, state, 0, 0, 0, 0, 0
        )

    def get_battery(self):
        if not self.connected:
            return None
        try:
            msg = self.master.recv_match(type='BATTERY_STATUS', blocking=True, timeout=1.0)
            return msg.battery_remaining if msg else None
        except:
            return None

    def disconnect(self):
        self.connected = False
        if self.master:
            try: self.master.close()
            except: pass
        print("[PIXHAWK-SITL] Disconnected.")