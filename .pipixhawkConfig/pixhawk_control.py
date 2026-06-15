import socket
import json
import time
import math
import threading
from pymavlink import mavutil

# --- Hardware Configuration ---
SERVO_PIN = 13
SERVO_OPEN = 1900  # PWM value to open the valve/start the pump
SERVO_CLOSED = 1100  # PWM value to close the valve/stop the pump

# 1. Setup UDP Listener
UDP_IP = "0.0.0.0"  # Listen on all Wi-Fi interfaces
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

mission_aborted = threading.Event()  # Global safety switch
spraying = False
spray_lock = threading.Lock()

# 2. Connect to the Virtual Drone (Change to '/dev/serial0' for real hardware later)
print("Connecting to drone...")
master = mavutil.mavlink_connection('tcp:127.0.0.1:5762')
master.wait_heartbeat()
print("Connected to Drone!")

# Wake up position stream
master.mav.request_data_stream_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_POSITION,
    5, 1  # Request updates at 5 Hz, 1 = Start sending
)


def set_flight_mode(mode_name):
    modes = {"GUIDED": 4, "LAND": 9, "BRAKE": 17}
    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        modes.get(mode_name)
    )


def fly_to_point(north, east, down):
    print(f"\nFlying to point: North {north}m, East {east}m...")
    global mission_aborted, spraying

    while True:
        # Safety Check: If background thread flagged an abort, stop navigation immediately
        if mission_aborted.is_set():
            print("[SAFETY] Flight loop broken for landing sequence.")
            break

        if spraying:
            time.sleep(0.5)
            continue

        # Remind the drone where to go (Position Only Mask lets Pixhawk handle throttle smoothly)
        master.mav.set_position_target_local_ned_send(
            0, master.target_system, master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            int(0b110111111000),  # Position only mask
            north, east, down,
            0, 0, 0, 0, 0, 0, 0, 0
        )

        # Ask for position with a 0.2s timeout so we never freeze
        msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=0.2)

        if msg:
            # Calculate distance safely using Pythagorean theorem
            dx = msg.x - north
            dy = msg.y - east

            # Prevent math domain errors from absolute zero or rounding glitches
            try:
                distance = math.sqrt(dx * dx + dy * dy)
            except ValueError:
                distance = 0.0

            # Print the distance cleanly on one line so you can watch it move!
            print(f"Distance to target: {distance:.1f}m    ", end='\r')

            if distance < 1.0:
                print("\nPoint reached!")
                break

        # Throttles the loop to 10Hz so we don't accidentally DDoS the Pixhawk data buffer!
        time.sleep(0.1)


def trigger_pump(duration):
    global spraying

    with spray_lock:

        if spraying:
            print("[PUMP] Spray request ignored, already spraying.")
            return

        if mission_aborted.is_set():
            return

        spraying = True

        try:
            print(f"\n[PUMP] Opening servo {SERVO_PIN} for {duration} seconds...")

            # BRAKE
            master.mav.set_mode_send(
                master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                17
            )

            time.sleep(2.5)

            # Open
            print(f"--- [HARDWARE TIME] Valve OPENED at: {time.strftime('%H:%M:%S')} ---")
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                0,
                SERVO_PIN,
                SERVO_OPEN,
                0,0,0,0,0
            )

            time.sleep(duration)

            print(f"--- [HARDWARE TIME] Valve CLOSED at: {time.strftime('%H:%M:%S')} ---")
            # Close
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                0,
                SERVO_PIN,
                SERVO_CLOSED,
                0,0,0,0,0
            )

            print("[PUMP] Spray complete.")

            set_flight_mode("GUIDED")

        finally:
            spraying = False


def command_listener():
    """Runs in the background. Listens for SPRAY and ABORT commands while the drone is flying."""
    global mission_aborted  # Pulling in global variable to ensure visibility across threads
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            payload = json.loads(data.decode('utf-8'))

            if payload.get("command") == "SPRAY":
                dur = payload.get("duration", 2.0)
                threading.Thread(target=trigger_pump, args=(dur,), daemon=True).start()

            elif payload.get("command") == "ABORT":
                print("\n[EMERGENCY] Abort received from Ground PC! Forcing LAND mode...")
                mission_aborted.set()
                set_flight_mode("LAND")

        except Exception as e:
            pass  # Ignore random network noise


# 3. Wait for the Ground PC to send the start command
while True:
    data, addr = sock.recvfrom(1024)
    payload = json.loads(data.decode('utf-8'))

    if payload.get("command") == "START_SCAN":
        field_width = payload["width"]
        field_length = payload["length"]
        print(f"Received scan dimensions: {field_width}m x {field_length}m")
        break

# 4. START THE BACKGROUND LISTENER NOW
threading.Thread(target=command_listener, daemon=True).start()

# 5. Generate the Lawnmower Path
scan_width = 2
waypoints = []
x = 0
y = 0
direction = 1

while y <= field_width:
    waypoints.append((x, y, -1))
    x = field_length if direction == 1 else 0
    waypoints.append((x, y, -1))
    y += scan_width
    direction *= -1

# 6. Execute the Flight
set_flight_mode("GUIDED")
time.sleep(1)

print("Arming and Taking off...")
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
master.motors_armed_wait()

master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 1)

print("Waiting for takeoff altitude...")

while True:

    msg = master.recv_match(
        type='LOCAL_POSITION_NED',
        blocking=True,
        timeout=1
    )

    if msg:

        altitude = -msg.z

        if altitude >= 0.8:
            print("\nTakeoff complete.")
            break

# --- CORRECTED PARAMETER BLOCK ---
# Note: If your simulation uses an older ArduCopter firmware, swap 'WP_SPEED' to 'WPNAV_SPEED' and 0.3 to 30.
print("Configuring safety parameters...")
master.mav.param_set_send(
    master.target_system, master.target_component,
    b'WP_SPD',
    0.3,
    mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)
time.sleep(0.2)

master.mav.param_set_send(
    master.target_system, master.target_component,
    b'WP_SPD_UP',
    0.3,
    mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)
time.sleep(0.2)

master.mav.param_set_send(
    master.target_system, master.target_component,
    b'WP_SPD_DN',
    0.3,
    mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)
time.sleep(1)
# ---------------------------------

try:
    for point in waypoints:

        if mission_aborted.is_set():
            print("[MISSION] Abort flag detected.")
            break

        fly_to_point(point[0], point[1], point[2])

    print("Scan complete. Landing normally...")
    set_flight_mode("LAND")

except KeyboardInterrupt:
    print("\n[EMERGENCY] Mission aborted by user! Landing immediately...")
    set_flight_mode("LAND")

except Exception as e:
    print(f"\n[CRITICAL ERROR] A software error occurred: {e}")
    print("Initiating emergency landing...")
    set_flight_mode("LAND")