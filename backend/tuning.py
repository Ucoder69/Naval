import threading
import backend.config as config
import time

class Tuner:
    """
    Controls runtime transfer parameters safely.
    Ensures mode changes NEVER break active transfers.
    """

    def __init__(self):
        self.lock = threading.Lock()

        # --- Runtime config ---
        self.chunk_size = 2 * 1024 * 1024   # 2 MB
        self.queue_size = 32
        self.mode = "balanced"
        self.ping = ""
        self.turbo = False

        # --- Session control ---
        self.session_id = 0
        self.transfer_active = False

        # --- Probing ----
        self.probe_event = threading.Event()
        self.probe_sent_time = 0.0
        self.probe_rtt = 0.0

    def begin_transfer(self):
        """Called when a file transfer starts"""
        with self.lock:
            self.transfer_active = True

    def end_transfer(self):
        """Called when a file transfer ends"""
        with self.lock:
            self.transfer_active = False
    def apply_ping(self, ping: str):
        self.ping = ping

    def handle_pong(self):
        """Call this inside receiver_loop when 'PONG' arrives."""
        self.probe_rtt = time.time() - self.probe_sent_time
        self.probe_event.set()

    def auto_tune(self, conn, send_system_fn, send_queue):
        """Sends RTT probe, measures ping, and automatically applies optimal mode."""
        self.probe_event.clear()
        self.probe_sent_time = time.time()

        send_system_fn(conn, "PING")

        # Fallback if peer doesn't respond in time
        if not self.probe_event.wait(timeout=2.0):
            print("[Timeout] Probe got timed out")
            self.apply_mode("balanced")
            send_queue.maxsize = self.queue_size
            return

        rtt_ms = self.probe_rtt * 1000
        self.apply_ping(int(rtt_ms))

        if rtt_ms < 4 :
            self.apply_mode("turbo+")
        elif rtt_ms <= 10:
            self.apply_mode("turbo")
        else:
            self.apply_mode("balanced")

        config.set_mode(self.mode)
        send_queue.maxsize = self.queue_size

    def apply_mode(self, mode: str):
        """
        Apply a mode safely.
        Mode changes only affect NEXT transfer.
        """
        with self.lock:
            if self.transfer_active:
                return False, "Cannot change mode during active transfer"

            if mode == "balanced":
                self.turbo = False
                self.chunk_size = 2 * 1024 * 1024
                self.queue_size = 32
                self.mode= mode       

            elif mode == "normal":
                self.turbo = False
                self.chunk_size = 3 * 1024 * 1024
                self.queue_size = 32
                self.mode= mode  

            elif mode == "turbo":
                self.turbo = True
                self.chunk_size = 4 * 1024 * 1024     # 4 MB
                self.queue_size = 64
                self.mode= mode

            elif mode == "turbo+":
                self.turbo = True
                self.chunk_size = 8 * 1024 * 1024     # 8 MB
                self.queue_size = 128
                self.mode= mode
            else:
                return False, "Unknown mode"

            # NEW logical session
            self.session_id += 1
            config.set_mode(self.mode)
            return True, f"Mode set to {mode.upper()} (session {self.session_id})"

    def status(self):
        with self.lock:
            return (
                f"Mode: {self.mode.capitalize()} | "
                f"Chunk: {self.chunk_size // 1024// 1024}MB | "
                f"Queue: {self.queue_size} | "
                f"Ping: {int(self.ping)}ms | "
                f"Session: {self.session_id}"
            )
