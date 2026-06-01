"""
test_full_mission.py
Full mission simulation using SITL.

Two waypoint modes:
  1. Load from Mission Planner — plan waypoints in Flight Plan tab, upload them,
     then this script reads and flies them
  2. Auto grid — enter field width, length, spacing and it generates a
     lawnmower pattern automatically

Run SITL in Mission Planner before running this.
"""

from pymavlink import mavutil
import time
import random
import csv
import math
from datetime import datetime


class MissionRunner:
    def __init__(self, port='tcp:127.0.0.1:5762'):
        self.master = None
        self.port = port
        self.detection_log = []
        self.flight_path = []
        self.pump_count = 0
        self.waypoints = []

    # ------------------------------------------------------------------ connect
    def connect(self):
        print("[SITL] Connecting...")
        self.master = mavutil.mavlink_connection(self.port)
        self.master.wait_heartbeat(timeout=10)
        print(f"[SITL] Connected! System ID: {self.master.target_system}")

        self.master.mav.request_data_stream_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            10, 1
        )
        time.sleep(2)

    # ------------------------------------------------------------------ GPS
    def get_gps(self):
        gps = None
        while True:
            msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=False)
            if msg is None:
                break
            if msg.lat != 0:
                gps = {
                    "lat": msg.lat / 1e7,
                    "lon": msg.lon / 1e7,
                    "alt": msg.relative_alt / 1000.0
                }

        if gps is None:
            msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=5)
            if msg and msg.lat != 0:
                gps = {
                    "lat": msg.lat / 1e7,
                    "lon": msg.lon / 1e7,
                    "alt": msg.relative_alt / 1000.0
                }
        return gps

    def wait_for_gps(self):
        print("[GPS] Waiting for fix...")
        for i in range(30):
            gps = self.get_gps()
            if gps:
                print(f"[GPS] Fix: {gps['lat']:.6f}, {gps['lon']:.6f}, alt {gps['alt']:.1f}m")
                return gps
            print(f"  Attempt {i + 1}...")
            time.sleep(1)
        print("[GPS] No fix after 30 attempts!")
        return None

    # ==================================================================
    # OPTION 1: Load waypoints from Mission Planner
    # ==================================================================
    def load_from_mission_planner(self):
        """
        Reads waypoints that are already uploaded to SITL via Mission Planner.

        How to use:
          1. In Mission Planner go to Flight Plan tab
          2. Click waypoints on the map to create your path
          3. Click 'Write WPs' to upload them to SITL
          4. Then run this script and choose option 1
        """
        print("[MISSION] Reading waypoints from Mission Planner...")

        # Request waypoint count
        self.master.waypoint_request_list_send()
        count_msg = self.master.recv_match(type='MISSION_COUNT', blocking=True, timeout=5)

        if not count_msg:
            print("[MISSION] No mission found! Upload waypoints in Mission Planner first.")
            return False

        total = count_msg.count
        print(f"[MISSION] Found {total} waypoints")

        self.waypoints = []
        for i in range(total):
            self.master.waypoint_request_send(i)
            wp = self.master.recv_match(
                type=['MISSION_ITEM', 'MISSION_ITEM_INT'],
                blocking=True, timeout=5
            )
            if not wp:
                print(f"[MISSION] Failed to read waypoint {i}")
                return False

            # Extract coordinates
            if wp.get_type() == 'MISSION_ITEM_INT':
                lat = wp.x / 1e7
                lon = wp.y / 1e7
            else:
                lat = wp.x
                lon = wp.y
            alt = wp.z

            # Skip home waypoint (index 0) if it has the same coords as current pos
            if i == 0:
                print(f"  Home: {lat:.6f}, {lon:.6f}, alt {alt:.1f}m")
                continue

            self.waypoints.append((lat, lon, alt))
            print(f"  WP {i}: {lat:.6f}, {lon:.6f}, alt {alt:.1f}m")

        print(f"[MISSION] Loaded {len(self.waypoints)} waypoints from Mission Planner")
        return True

    # ==================================================================
    # OPTION 2: Auto-generate lawnmower grid
    # ==================================================================
    def generate_grid(self, home_lat, home_lon, width_m, height_m, spacing_m, alt):
        """
        Generates a lawnmower pattern over a rectangular field.

        The drone flies:
          start → bottom → shift right → top → shift right → bottom → ...
          then returns to start.

        Parameters:
          width_m:   field width in metres (east-west)
          height_m:  field height in metres (north-south)
          spacing_m: distance between parallel flight lines
          alt:       flight altitude in metres
        """
        lat_per_m = 1.0 / 111111.0
        lon_per_m = 1.0 / (111111.0 * math.cos(math.radians(home_lat)))

        self.waypoints = []
        num_lines = int(width_m / spacing_m) + 1
        left_to_right = True

        print(f"\n[PATH] Generating grid:")
        print(f"  Field size:  {width_m}m x {height_m}m")
        print(f"  Spacing:     {spacing_m}m between lines")
        print(f"  Altitude:    {alt}m")
        print(f"  Lines:       {num_lines}")

        for i in range(num_lines):
            lon_offset = i * spacing_m * lon_per_m

            if left_to_right:
                # Top to bottom
                self.waypoints.append((home_lat, home_lon + lon_offset, alt))
                self.waypoints.append((home_lat - height_m * lat_per_m, home_lon + lon_offset, alt))
            else:
                # Bottom to top
                self.waypoints.append((home_lat - height_m * lat_per_m, home_lon + lon_offset, alt))
                self.waypoints.append((home_lat, home_lon + lon_offset, alt))

            left_to_right = not left_to_right

        # Add return to start as final waypoint
        self.waypoints.append((home_lat, home_lon, alt))

        print(f"  Waypoints:   {len(self.waypoints)} (including return to start)")

        for i, (lat, lon, a) in enumerate(self.waypoints):
            label = "START" if i == 0 else "RTL" if i == len(self.waypoints) - 1 else ""
            print(f"    WP {i + 1}: {lat:.6f}, {lon:.6f}, {a:.0f}m  {label}")

        return True

    # ------------------------------------------------------------------ upload
    def upload_mission(self):
        """Upload self.waypoints to SITL."""
        if not self.waypoints:
            print("[MISSION] No waypoints to upload!")
            return False

        print(f"\n[MISSION] Uploading {len(self.waypoints)} waypoints...")

        self.master.waypoint_clear_all_send()
        self.master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)

        total = len(self.waypoints) + 1  # +1 for home
        self.master.waypoint_count_send(total)

        for i in range(total):
            msg = self.master.recv_match(
                type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'],
                blocking=True, timeout=5
            )
            if not msg:
                print(f"[MISSION] No request for waypoint {i}")
                return False

            if i == 0:
                lat, lon, alt = self.waypoints[0]
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    0,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 1, 0, 0, 0, 0,
                    int(lat * 1e7), int(lon * 1e7), alt
                )
            else:
                lat, lon, alt = self.waypoints[i - 1]
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    i,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 1, 0, 0, 0, 0,
                    int(lat * 1e7), int(lon * 1e7), alt
                )

        ack = self.master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
        print(f"[MISSION] Upload complete!")
        return True

    # ------------------------------------------------------------------ flight
    def arm_and_takeoff(self, target_alt=10):
        print("[FLIGHT] Setting GUIDED mode...")
        self.master.set_mode('GUIDED')
        time.sleep(2)

        print("[FLIGHT] Arming...")
        self.master.arducopter_arm()
        self.master.motors_armed_wait()
        print("[FLIGHT] Armed!")

        print(f"[FLIGHT] Taking off to {target_alt}m...")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0, 0, 0, 0, 0, 0, 0, target_alt
        )

        for i in range(60):
            # Drain all pending messages to stay current
            while self.master.recv_match(blocking=False):
                pass

            msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
            if msg:
                alt = msg.relative_alt / 1000.0
                print(f"  Altitude: {alt:.1f}m / {target_alt}m")
                if alt >= target_alt * 0.9:
                    print(f"[FLIGHT] Reached target altitude!")
                    return True
            time.sleep(0.5)

        print("[FLIGHT] Takeoff timed out")
        return False

    def start_mission(self):
        print("[FLIGHT] Switching to AUTO mode — flying mission...")
        self.master.set_mode('AUTO')

    def return_to_launch(self):
        print("[FLIGHT] Returning to launch...")
        self.master.set_mode('RTL')

    # ------------------------------------------------------------------ pump
    def fire_pump(self, gps):
        self.pump_count += 1

        self.detection_log.append({
            "time": datetime.now().isoformat(),
            "lat": gps["lat"],
            "lon": gps["lon"],
            "alt": gps["alt"],
            "detection_num": self.pump_count
        })

        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_RELAY,
            0, 0, 1, 0, 0, 0, 0, 0
        )
        print(f"  [PUMP] ON — detection #{self.pump_count} at {gps['lat']:.6f}, {gps['lon']:.6f}")
        time.sleep(2)

        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_RELAY,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        print(f"  [PUMP] OFF")

    # ------------------------------------------------------------------ monitor
    def monitor_mission(self, detection_chance=0.15):
        print(f"\n[MONITOR] Monitoring flight (simulated detection chance: {detection_chance * 100:.0f}%)")
        print("[MONITOR] Watch the drone in Mission Planner!\n")

        last_wp = -1
        no_gps_count = 0

        while True:
            # Drain stale messages
            while self.master.recv_match(blocking=False):
                pass

            gps = self.get_gps()
            if not gps:
                no_gps_count += 1
                if no_gps_count > 10:
                    print("[MONITOR] Lost GPS for too long — ending monitor")
                    break
                time.sleep(1)
                continue
            no_gps_count = 0

            self.flight_path.append({
                "lat": gps["lat"],
                "lon": gps["lon"],
                "alt": gps["alt"]
            })

            # Check which waypoint we're heading to
            wp_msg = self.master.recv_match(type='MISSION_CURRENT', blocking=False)
            if wp_msg:
                current_wp = wp_msg.seq
                if current_wp != last_wp:
                    print(f"[NAV] Heading to waypoint {current_wp} | "
                          f"GPS: {gps['lat']:.6f}, {gps['lon']:.6f}, alt: {gps['alt']:.1f}m")
                    last_wp = current_wp

            # Simulate random detection
            if random.random() < detection_chance:
                print(f"\n  *** WEED DETECTED! ***")
                self.fire_pump(gps)
                print()

            # Check if mission is done
            heartbeat = self.master.recv_match(type='HEARTBEAT', blocking=False)
            if heartbeat:
                mode = mavutil.mode_string_v10(heartbeat)
                if mode not in ['AUTO', 'GUIDED']:
                    print(f"[MONITOR] Mode changed to {mode} — mission complete")
                    break

            # Check if we reached last waypoint
            if wp_msg and wp_msg.seq >= len(self.waypoints):
                print("[MONITOR] All waypoints reached!")
                break

            time.sleep(2)

    # ------------------------------------------------------------------ save
    def save_results(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if self.detection_log:
            det_file = f"sim_detections_{timestamp}.csv"
            with open(det_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["time", "lat", "lon", "alt", "detection_num"])
                writer.writeheader()
                writer.writerows(self.detection_log)
            print(f"[SAVE] Detections → {det_file}")

        if self.flight_path:
            path_file = f"sim_flightpath_{timestamp}.csv"
            with open(path_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["lat", "lon", "alt"])
                writer.writeheader()
                writer.writerows(self.flight_path)
            print(f"[SAVE] Flight path → {path_file}")

    # ------------------------------------------------------------------ plot
    def plot_results(self):
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("[PLOT] matplotlib not installed — skipping")
            return

        fig, ax = plt.subplots(figsize=(10, 8))
        fig.patch.set_facecolor("#0F1117")
        ax.set_facecolor("#1A1D27")

        # Flight path
        if self.flight_path:
            lats = [p["lat"] for p in self.flight_path]
            lons = [p["lon"] for p in self.flight_path]
            ax.plot(lons, lats, color="#4B5563", linewidth=1.5, alpha=0.6, label="Flight path")

        # Waypoints
        if self.waypoints:
            wp_lats = [w[0] for w in self.waypoints]
            wp_lons = [w[1] for w in self.waypoints]
            ax.scatter(wp_lons, wp_lats, color="#60A5FA", s=50, zorder=4,
                       marker="s", label=f"Waypoints ({len(self.waypoints)})")

            # Number each waypoint
            for i, (lat, lon, _) in enumerate(self.waypoints):
                ax.annotate(str(i + 1), (lon, lat), textcoords="offset points",
                            xytext=(6, 6), color="#60A5FA", fontsize=7)

        # Detections
        if self.detection_log:
            det_lats = [d["lat"] for d in self.detection_log]
            det_lons = [d["lon"] for d in self.detection_log]
            ax.scatter(det_lons, det_lats, color="#EF4444", s=120, zorder=5,
                       marker="X", label=f"Detections ({len(self.detection_log)})")
            for d in self.detection_log:
                ax.annotate(f"#{d['detection_num']}", (d["lon"], d["lat"]),
                            textcoords="offset points", xytext=(8, 8),
                            color="#E8EAF0", fontsize=8)

        ax.set_xlabel("Longitude", color="#6B7280")
        ax.set_ylabel("Latitude", color="#6B7280")
        ax.set_title(f"Mission Results — {len(self.detection_log)} detections, {self.pump_count} sprays",
                     color="#E8EAF0", fontsize=13, fontweight="bold")
        ax.tick_params(colors="#6B7280")
        ax.legend(facecolor="#1A1D27", labelcolor="#E8EAF0", edgecolor="#2A2D3A")
        ax.grid(True, color="#2A2D3A", linewidth=0.5)

        plt.tight_layout()
        plt.savefig("sim_mission_map.png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        print("[PLOT] Map saved to sim_mission_map.png")
        plt.show()


# ================================================================== menu
def get_user_choice():
    print("\n" + "=" * 50)
    print("  AgriDrone — Mission Planner")
    print("=" * 50)
    print()
    print("  1. Load waypoints from Mission Planner")
    print("     (plan your route in Flight Plan tab first)")
    print()
    print("  2. Auto-generate lawnmower grid")
    print("     (enter field dimensions, grid is created automatically)")
    print()

    while True:
        choice = input("  Choose mode (1 or 2): ").strip()
        if choice in ['1', '2']:
            return int(choice)
        print("  Please enter 1 or 2.")


def get_grid_params():
    print("\n  Enter field dimensions:")

    while True:
        try:
            width = float(input("    Field width  (metres): "))
            length = float(input("    Field length (metres): "))
            spacing = float(input("    Line spacing (metres, e.g. 5): "))
            alt = float(input("    Flight altitude (metres, e.g. 10): "))

            if width <= 0 or length <= 0 or spacing <= 0 or alt <= 0:
                print("    All values must be positive.")
                continue
            if spacing > min(width, length):
                print("    Spacing can't be larger than the field.")
                continue

            return width, length, spacing, alt
        except ValueError:
            print("    Please enter valid numbers.")


# ================================================================== main
def main():
    runner = MissionRunner(port='tcp:127.0.0.1:5762')

    # 1. Connect
    runner.connect()

    # 2. Wait for GPS
    home = runner.wait_for_gps()
    if not home:
        return

    # 3. Choose waypoint mode
    choice = get_user_choice()

    if choice == 1:
        # Load from Mission Planner
        if not runner.load_from_mission_planner():
            print("\nNo waypoints found. Create waypoints in Mission Planner's")
            print("Flight Plan tab and click 'Write WPs' first.")
            return
        alt = runner.waypoints[0][2] if runner.waypoints else 10

    elif choice == 2:
        # Auto-generate grid
        width, length, spacing, alt = get_grid_params()
        runner.generate_grid(
            home_lat=home["lat"],
            home_lon=home["lon"],
            width_m=width,
            height_m=length,
            spacing_m=spacing,
            alt=alt
        )

    # 4. Upload mission to SITL
    if not runner.upload_mission():
        print("Failed to upload mission!")
        return

    # 5. Confirm before flight
    print(f"\n  Ready to fly {len(runner.waypoints)} waypoints at {alt}m altitude.")
    confirm = input("  Start mission? (y/n): ").strip().lower()
    if confirm != 'y':
        print("  Mission cancelled.")
        return

    # 6. Arm and takeoff
    if not runner.arm_and_takeoff(target_alt=alt):
        print("Takeoff failed!")
        return

    # 7. Fly the mission
    runner.start_mission()

    # 8. Monitor and detect
    runner.monitor_mission(detection_chance=0.15)

    # 9. Return to launch
    runner.return_to_launch()
    print("[FLIGHT] Waiting for landing...")
    time.sleep(15)

    # 10. Results
    print("\n" + "=" * 50)
    print("  MISSION COMPLETE")
    print("=" * 50)
    print(f"  Waypoints flown: {len(runner.waypoints)}")
    print(f"  Detections:      {len(runner.detection_log)}")
    print(f"  Pump triggers:   {runner.pump_count}")
    print(f"  Path points:     {len(runner.flight_path)}")
    print("=" * 50)

    runner.save_results()
    runner.plot_results()


if __name__ == "__main__":
    main()