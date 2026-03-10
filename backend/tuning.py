# tuner.py
import threading

class Tuner:
    """
    Controls runtime transfer parameters safely.
    Ensures mode changes NEVER break active transfers.
    """

    def __init__(self):
        self.lock = threading.Lock()

        # --- Runtime config ---
        self.chunk_size = 2 * 1024 * 1024   # 512 KB
        self.queue_size = 64
        self.mode= "balanced-"
        self.turbo = False

        # --- Session control ---
        self.session_id = 0
        self.transfer_active = False

    def begin_transfer(self):
        """Called when a file transfer starts"""
        with self.lock:
            self.transfer_active = True

    def end_transfer(self):
        """Called when a file transfer ends"""
        with self.lock:
            self.transfer_active = False

    def apply_mode(self, mode: str):
        """
        Apply a mode safely.
        Mode changes only affect NEXT transfer.
        """
        with self.lock:
            if self.transfer_active:
                return False, "Cannot change mode during active transfer"

            if mode == "turbo":
                self.turbo = True
                self.chunk_size = 4 * 1024 * 1024     # 4 MB
                self.queue_size = 128
                self.mode= mode

            elif mode == "normal":
                self.turbo = False
                self.chunk_size = 3 * 1024 * 1024
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
            return True, f"Mode set to {mode.upper()} (session {self.session_id})"

    def status(self):
        with self.lock:
            return (
                f"Mode: {self.mode} | "
                f"Chunk: {self.chunk_size // 1024// 1024} MB | "
                f"Queue: {self.queue_size} | "
                f"Session: {self.session_id}"
            )