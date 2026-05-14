import paramiko
import time


class PiConnector:
    def __init__(self):
        self.PI_IP       = "raspberrypi.local"
        self.PI_USER     = "pi"
        self.PI_PASSWORD = ""
        self.SENDER_PATH = "/home/pi/Desktop/live_test/demo_v2.py"

        self.client = None

    def connect_and_start(self):
        try:
            print("[SSH] Connecting to Pi...")
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                self.PI_IP,
                username=self.PI_USER,
                password=self.PI_PASSWORD,
                timeout=10
            )
            print("[SSH] Connected.")

            # Kill any existing sender process
            self.client.exec_command("pkill -f demo_v2.py")
            time.sleep(1)

            # Start sender with auto-restart wrapper
            self.client.exec_command(
                    "nohup /home/pi/start_sender.sh > /home/pi/Desktop/live_test/sender.log 2>&1 &"

            )
            time.sleep(2)
            print("[SSH] Sender started on Pi.")
            return True

        except Exception as e:
            print(f"[SSH] Failed: {e}")
            return False

    def stop_sender(self):
        try:
            if self.client:
                # Kill both the shell script loop and the sender itself
                self.client.exec_command("pkill -f start_sender.sh")
                self.client.exec_command("pkill -f demo_v2.py")
                print("[SSH] Sender stopped on Pi.")
        except Exception as e:
            print(f"[SSH] Could not stop sender: {e}")
        finally:
            self.disconnect()

    def disconnect(self):
        try:
            if self.client:
                self.client.close()
                self.client = None
        except:
            pass