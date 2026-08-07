"""
SSH automation for the Raspberry Pi.

Starts and stops pi/sender.py on the Pi so the operator only has to press
"Start mission" in the GUI. Credentials come from config.json / environment
variables (see config.py) — nothing is hardcoded here.
"""

import time

import paramiko

import config


class PiConnector:
    def __init__(self, cfg=None):
        cfg = cfg or config.load_config()
        pi = cfg["pi"]

        self.host = pi["host"]
        self.port = int(pi["port"])
        self.user = pi["user"]
        self.password = pi["password"] or None
        self.key_file = pi["key_file"] or None
        self.remote_dir = pi["remote_dir"].rstrip("/")
        self.auto_start = bool(pi.get("auto_start", True))

        self.sender_path = f"{self.remote_dir}/sender.py"
        self.wrapper_path = f"{self.remote_dir}/start_sender.sh"
        self.log_path = f"{self.remote_dir}/sender.log"

        self.client = None
        self.last_error = None

    # ------------------------------------------------------------------ connect
    def connect(self):
        """Open an SSH session. Returns True on success."""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.client.connect(
                self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                key_filename=self.key_file,
                timeout=10,
                allow_agent=self.password is None,
                look_for_keys=self.password is None,
            )
            return True
        except paramiko.AuthenticationException:
            self.last_error = (
                f"SSH authentication failed for {self.user}@{self.host}. "
                "Check pi.user / pi.password (or pi.key_file) in config.json."
            )
        except Exception as exc:
            self.last_error = (
                f"Could not reach {self.user}@{self.host}:{self.port} ({exc}). "
                "Is the Pi powered on and connected to the hotspot?"
            )
        self.client = None
        return False

    def connect_and_start(self):
        """Connect to the Pi and launch the sender. Returns True on success."""
        if not self.auto_start:
            print("[SSH] pi.auto_start is false — start the sender yourself.")
            return True

        print(f"[SSH] Connecting to {self.user}@{self.host} ...")
        if not self.connect():
            print(f"[SSH] {self.last_error}")
            return False
        print("[SSH] Connected.")

        if not self._remote_file_exists(self.wrapper_path):
            self.last_error = (
                f"{self.wrapper_path} is missing on the Pi. "
                "Deploy it first: python tools/deploy_pi.py"
            )
            print(f"[SSH] {self.last_error}")
            self.disconnect()
            return False

        # Kill any sender left over from a previous session
        self._run(f"pkill -f {self.wrapper_path}; pkill -f {self.sender_path}")
        time.sleep(1)

        self._run(f"nohup {self.wrapper_path} > {self.log_path} 2>&1 &")
        time.sleep(2)

        if not self._sender_running():
            tail = self._run(f"tail -n 20 {self.log_path}")[0]
            self.last_error = f"Sender did not start. Log said:\n{tail.strip()}"
            print(f"[SSH] {self.last_error}")
            self.disconnect()
            return False

        print("[SSH] Sender running on the Pi.")
        return True

    # ------------------------------------------------------------------ control
    def stop_sender(self):
        try:
            if self.client is None and self.auto_start:
                self.connect()
            if self.client is not None:
                self._run(f"pkill -f {self.wrapper_path}; pkill -f {self.sender_path}")
                print("[SSH] Sender stopped on the Pi.")
        except Exception as exc:
            print(f"[SSH] Could not stop sender: {exc}")
        finally:
            self.disconnect()

    def read_log(self, lines=30):
        """Return the tail of the sender log, for troubleshooting."""
        if self.client is None and not self.connect():
            return self.last_error
        return self._run(f"tail -n {lines} {self.log_path}")[0]

    def disconnect(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    # ------------------------------------------------------------------ internals
    def _run(self, command):
        """Run a command on the Pi and return (stdout, stderr)."""
        _, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        return out, err

    def _remote_file_exists(self, path):
        out, _ = self._run(f"test -f {path} && echo yes || echo no")
        return out.strip() == "yes"

    def _sender_running(self):
        out, _ = self._run(f"pgrep -f {self.sender_path} || true")
        return bool(out.strip())
