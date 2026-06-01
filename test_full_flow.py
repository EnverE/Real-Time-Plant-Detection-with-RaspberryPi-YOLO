from pymavlink import mavutil
import time

print("Connecting...")
master = mavutil.mavlink_connection('tcp:127.0.0.1:5762')
master.wait_heartbeat()
print(f"Connected! System ID: {master.target_system}")

# Request SITL to send all data streams
print("Requesting data streams...")
master.mav.request_data_stream_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_ALL,
    10,  # 10 Hz
    1    # start
)

time.sleep(2)

# Now try GPS
print("Reading GPS...")
for attempt in range(30):
    msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
    if msg and msg.lat != 0:
        print(f"GPS: {msg.lat/1e7:.6f}, {msg.lon/1e7:.6f}, alt {msg.relative_alt/1000:.1f}m")
        break
    print(f"  Attempt {attempt + 1}...")
else:
    print("Still no GPS. Printing all messages to see what's available...")
    for _ in range(20):
        msg = master.recv_match(blocking=True, timeout=2)
        if msg:
            print(f"  Got: {msg.get_type()}")
    exit(1)

# Test relay
print("\n--- Pump test ---")
for i in range(3):
    msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
    if msg:
        print(f"Detection #{i+1} at GPS: {msg.lat/1e7:.6f}, {msg.lon/1e7:.6f}")

    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_RELAY,
        0, 0, 1, 0, 0, 0, 0, 0
    )
    print("Pump ON")
    time.sleep(2)

    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_RELAY,
        0, 0, 0, 0, 0, 0, 0, 0
    )
    print("Pump OFF")
    time.sleep(3)

print("\nAll tests passed!")