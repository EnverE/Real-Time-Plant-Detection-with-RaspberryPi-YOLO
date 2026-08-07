# Pixhawk / drone control notes

Reference material for connecting the Raspberry Pi to a Pixhawk flight controller.
**None of this is wired into the detection pipeline yet.** The pump in the GUI is
simulated. `receiver._trigger_pump()` is where a real actuation command would go.

## Wiring

| Pixhawk | Raspberry Pi |
|---|---|
| TX | RX |
| RX | TX |
| GND | GND |

Pin diagrams: [PiPins.png](PiPins.png), [PixhawkPins.png](PixhawkPins.png).
The 5 V pin is not needed; the Pi runs from its own power source.

## Pi setup

```bash
sudo apt-get update && sudo apt-get upgrade
sudo apt-get install -y python3-pip python3-dev screen
pip3 install future pyserial dronekit PyYAML mavproxy
```

Then `sudo raspi-config` → **Interface Options** → Serial Port:

- login shell over serial: **disabled**
- serial port hardware: **enabled**

Disable Bluetooth so it stops claiming the UART. Add it to `/boot/config.txt`
(`/boot/firmware/config.txt` on Bookworm):

```
enable_uart=1
dtoverlay=disable-bt
```

Reboot, then check you can talk to the flight controller:

```bash
sudo mavproxy.py --master=/dev/ttyAMA0
```

You should land at a `STABILIZE>` prompt. `mode GUIDED` switches mode.

> `arm throttle` spins the motors. Remove the propellers before testing.

## Pixhawk side

The firmware was configured with Mission Planner and needs no changes for this.

## Example flight script

[`example_drone_control.py`](example_drone_control.py) is a standalone DroneKit
demo: arm, take off to 3 m, fly forward, land. It runs on the Pi, is not imported
by anything, and is included as a starting point only.

> Flying under script control is dangerous. Test with propellers removed, in a
> safe area, with a manual override on the transmitter ready.
