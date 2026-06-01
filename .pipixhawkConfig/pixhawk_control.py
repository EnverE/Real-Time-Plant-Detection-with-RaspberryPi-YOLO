import socket
import json
import time
import math
import threading
from pymavlink import mavutil

# --- Hardware Configuration ---
SERVO_PIN = 9
SERVO_OPEN = 1900  # PWM value to open the valve/start the pump
SERVO_CLOSED = 1100  # PWM value to close the valve/stop the pump

# 1. Setup UDP Listener
UDP_IP = "0.0.0.0"  # Listen on all Wi-Fi interfaces
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

mission_aborted=False

# 2. Connect to the Virtual Drone (Change to '/dev/serial0' for real hardware later)
print("Connecting to drone...")
master = mavutil.mavlink_connection('tcp:127.0.0.1:5762')
master.wait_heartbeat()
print("Connected to Drone!")

master.mav.request_data_stream_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_POSITION,
    5, 1 # Request updates at 5 Hz, 1 = Start sending
)

def set_flight_mode(mode_name):
    modes = {"GUIDED": 4, "LAND": 9}
    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        modes.get(mode_name)
    )


def fly_to_point(north, east, down):
    print(f"Flying to point: North {north}m, East {east}m...")

    while True:
        #Remind the drone where to go
        master.mav.set_position_target_local_ned_send(
            0, master.target_system, master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            int(0b110111111000),
            north, east, down,
            0, 0, 0, 0, 0, 0, 0, 0
        )

        # Ask for position with a 0.2s timeout so we never freeze
        msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=0.2)

        if msg:
            # Calculate distance using Pythagorean theorem
            dx = msg.x - north
            dy = msg.y - east
            distance = math.sqrt(dx * dx + dy * dy)

            # Print the distance cleanly on one line so you can watch it move!
            print(f"Distance to target: {distance:.1f}m", end='\r')

            if distance < 1.0:
                print("\nPoint reached!")
                break


def trigger_pump(duration):
    """Commands the Pixhawk to open the servo, waits, and closes it."""
    print(f"[PUMP] Opening servo {SERVO_PIN} for {duration} seconds...")

    # Switch to BRAKE mode (Mode 17 in ArduCopter)
    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        17
    )
    time.sleep(1.5)  # Give the drone a moment to completely stop moving

    # Open Servo
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
        SERVO_PIN, SERVO_OPEN, 0, 0, 0, 0, 0
    )

    # Wait for the duration requested by the Ground PC
    time.sleep(duration)

    # Close Servo
    print(f"[PUMP] Closing servo {SERVO_PIN}.")
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO, 0,
        SERVO_PIN, SERVO_CLOSED, 0, 0, 0, 0, 0
    )

    #resume
    set_flight_mode("GUIDED")


def command_listener():
    """Runs in the background. Listens for SPRAY and ABORT commands while the drone is flying."""
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            payload = json.loads(data.decode('utf-8'))

            if payload.get("command") == "SPRAY":
                dur = payload.get("duration", 2.0)
                # Run the pump in a quick micro-thread so it doesn't block incoming network traffic
                threading.Thread(target=trigger_pump, args=(dur,), daemon=True).start()

            elif payload.get("command") == "ABORT":
                print("\n[EMERGENCY] Abort received from Ground PC! Forcing LAND mode...")
                mission_aborted = True
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
scan_width = 3
waypoints = []
x = 0
y = 0
direction = 1

while y <= field_width:
    waypoints.append((x, y, -3))
    x = field_length if direction == 1 else 0
    waypoints.append((x, y, -3))
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
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 3)
time.sleep(5)

master.mav.param_set_send(
    master.target_system, master.target_component,
    b'WP_SPD',
    0.3,
    mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)

master.mav.param_set_send(
    master.target_system, master.target_component,
    b'WP_SP_UP',
    1,
    mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)

master.mav.param_set_send(
    master.target_system, master.target_component,
    b'WP_SPD_DN',
    0.5,
    mavutil.mavlink.MAV_PARAM_TYPE_REAL32
)

time.sleep(1)

try:
    for point in waypoints:
        fly_to_point(point[0], point[1], point[2])

    print("Scan complete. Landing normally...")
    set_flight_mode("LAND")

except KeyboardInterrupt:
    # This triggers if you click into the terminal and press Ctrl+C
    print("\n[EMERGENCY] Mission aborted by user! Landing immediately...")
    set_flight_mode("LAND")

except Exception as e:
    # This triggers if your code crashes, the math fails, or the network drops
    print(f"\n[CRITICAL ERROR] A software error occurred: {e}")
    print("Initiating emergency landing...")
    set_flight_mode("LAND")