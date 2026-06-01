from pymavlink import mavutil

ports = [
    'tcp:127.0.0.1:5760',
    'tcp:127.0.0.1:5762',
    'tcp:127.0.0.1:5763',
    'tcp:127.0.0.1:5770',
    'tcp:127.0.0.1:5780',
]

for port in ports:
    try:
        print(f"Trying {port}...")
        m = mavutil.mavlink_connection(port, timeout=5)
        m.wait_heartbeat(timeout=5)
        print(f"  HEARTBEAT on {port}!")

        msg = m.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=5)
        if msg and msg.lat != 0:
            print(f"  GPS: {msg.lat/1e7:.6f}, {msg.lon/1e7:.6f}")
        else:
            print(f"  No GPS on this port")
        m.close()
    except Exception as e:
        print(f"  Failed: {e}")

print("Done scanning.")