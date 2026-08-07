#!/usr/bin/env python3
"""
Copy the sender onto the Raspberry Pi over SSH.

Run this once after cloning, and again whenever pi/sender.py changes:

    python tools/deploy_pi.py            # copy the sender + its settings
    python tools/deploy_pi.py --install  # also run pi/install_pi.sh on the Pi

Connection details come from config.json (see config.example.json).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                     # noqa: E402
from pi_connector import PiConnector   # noqa: E402

PI_DIR = config.ROOT / "pi"
FILES = ["sender.py", "start_sender.sh", "install_pi.sh"]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install", action="store_true",
                        help="run install_pi.sh on the Pi after copying")
    args = parser.parse_args()

    cfg = config.load_config()
    pi = PiConnector(cfg)

    print(f"Connecting to {pi.user}@{pi.host}:{pi.port} ...")
    if not pi.connect():
        print(pi.last_error)
        return 1

    try:
        sftp = pi.client.open_sftp()
        _mkdir_p(sftp, pi.remote_dir)

        for name in FILES:
            local = PI_DIR / name
            remote = f"{pi.remote_dir}/{name}"
            sftp.put(str(local), remote)
            if name.endswith(".sh"):
                sftp.chmod(remote, 0o755)
            print(f"  uploaded {name}")

        # Bake the laptop address and camera settings into the Pi's own config
        sender_cfg = {
            "host": cfg["laptop"]["hotspot_ip"],
            "port": cfg["laptop"]["listen_port"],
            "width": cfg["camera"]["width"],
            "height": cfg["camera"]["height"],
            "fps": cfg["camera"]["fps"],
            "jpeg_quality": cfg["camera"]["jpeg_quality"],
            "camera": "auto",
        }
        with sftp.open(f"{pi.remote_dir}/sender_config.json", "w") as fh:
            fh.write(json.dumps(sender_cfg, indent=2))
        print("  wrote sender_config.json")
        sftp.close()

        if args.install:
            print("\nRunning install_pi.sh (this takes a few minutes) ...")
            _, stdout, stderr = pi.client.exec_command(
                f"bash {pi.remote_dir}/install_pi.sh", get_pty=True)
            for line in stdout:
                print("  " + line.rstrip())
            err = stderr.read().decode(errors="replace").strip()
            if err:
                print("  " + err)

        print(f"\nDone. Sender installed at {pi.remote_dir}/sender.py")
        print("Start a mission from the GUI, or test it directly on the Pi:")
        print(f"  ssh {pi.user}@{pi.host} python3 {pi.remote_dir}/sender.py")
        return 0
    finally:
        pi.disconnect()


def _mkdir_p(sftp, remote_dir):
    parts = remote_dir.strip("/").split("/")
    path = ""
    for part in parts:
        path += "/" + part
        try:
            sftp.stat(path)
        except FileNotFoundError:
            sftp.mkdir(path)


if __name__ == "__main__":
    sys.exit(main())
