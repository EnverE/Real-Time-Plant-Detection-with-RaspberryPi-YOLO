from dronekit import connect, VehicleMode
from pymavlink import mavutil
import time

# Connect to Pixhawk
# Change serial port if needed
vehicle = connect('/dev/serial0', baud=57600, wait_ready=True)

print("Connected")

# Wait until drone is armable
while not vehicle.is_armable:
    print("Waiting for vehicle...")
    time.sleep(1)

# Set GUIDED mode
vehicle.mode = VehicleMode("GUIDED")

while vehicle.mode.name != "GUIDED":
    print("Waiting for GUIDED mode...")
    time.sleep(1)

# Arm motors
vehicle.armed = True

while not vehicle.armed:
    print("Arming...")
    time.sleep(1)

print("Taking off")

# Takeoff to 3 meters
vehicle.simple_takeoff(3)

# Wait until altitude reached
while True:
    alt = vehicle.location.global_relative_frame.alt
    print(f"Altitude: {alt}")

    if alt >= 2.8:
        print("Target altitude reached")
        break

    time.sleep(1)

# Fly forward
msg = vehicle.message_factory.set_position_target_local_ned_encode(
    0,
    0,
    0,
    mavutil.mavlink.MAV_FRAME_BODY_NED,
    0b0000111111000111,
    0,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    0,
    0
)

print("Moving forward")

for _ in range(50):
    vehicle.send_mavlink(msg)
    time.sleep(0.1)

# Land
print("Landing")

vehicle.mode = VehicleMode("LAND")

while vehicle.armed:
    print("Landing...")
    time.sleep(1)

print("Done")

vehicle.close()