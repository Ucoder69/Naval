
import backend.protocol as protocol
import backend.transport as transport
import backend.encryption as en
from backend.tuning import Tuner
from backend.config import set_mode
import hashlib
import threading
import os
import time
from collections import deque
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

# Create a pool to match the sender's max_inflight
recv_pool = ThreadPoolExecutor(max_workers=max(1, os.cpu_count()//2))

conn_alive = True
TUNER = Tuner()
recv_ready = threading.Event()
ready_event = threading.Event()
send_queue = Queue(maxsize=64)

# ── Socket lock — prevents two threads writing simultaneously ─────────────────
_send_lock = threading.Lock()

def send_system(conn, message: str):
    payload = message.encode("utf-8")
    header = protocol.e_type("System") + protocol.e_length(len(payload))
    with _send_lock:
        conn.sendall(header)
        conn.sendall(payload)

def send_frame(conn, msg_type, payload: bytes):
    header = protocol.e_type(msg_type) + protocol.e_length(len(payload))
    with _send_lock:
        conn.sendall(header)
        conn.sendall(payload)
def handshake_auth(conn) -> tuple[bytes, str]:
    """Exchanges public keys, tests mutual key validity via encrypted handshake,

    and returns (shared_key, safety_code) or raises an exception to abort.
    """
    my_sk, my_pk = en.generate_keypair()
    my_pk_bytes = my_pk.encode()

    # 1. Send public key
    send_system(conn, f"PUBKEY:{my_pk_bytes.hex()}")

    # 2. Read peer public key
    peer_pk_bytes = None
    while not peer_pk_bytes:
        header = transport.read_exactly(conn, 5)
        l = protocol.d_length(header[1:5])
        payload = transport.read_exactly(conn, l).decode("utf-8")

        if payload.startswith("PUBKEY:"):
            peer_pk_bytes = bytes.fromhex(payload.split(":", 1)[1])

    # 3. Derive key and safety number
    shared_key = en.derive_shared_key(my_sk, peer_pk_bytes)
    safety_code = en.generate_safety_number(my_pk_bytes, peer_pk_bytes)

    # 4. Exchange encrypted AUTH tokens to test key integrity
    auth_token = b"VERIFY_KEY_INTEGRITY_OK"

    # Send encrypted ping
    encrypted_ping = en.encrypt_msg(shared_key, auth_token)
    send_frame(conn, "Text", encrypted_ping)

    # Receive peer encrypted ping
    header = transport.read_exactly(conn, 5)
    l = protocol.d_length(header[1:5])
    peer_payload = transport.read_exactly(conn, l)

    # 5. Validate decryption and payload match
    decrypted_token = en.decrypt_msg(shared_key, peer_payload)
    if decrypted_token != auth_token:
        raise ValueError("Handshake token mismatch!")

    return shared_key, safety_code

def network_sender(conn):
    while True:
        item = send_queue.get()
        if item is None:
            break

        # Check if item includes progress tracking metadata
        if len(item) == 4:
            msg_type, payload, raw_len, progress = item
            send_frame(conn, msg_type, payload)
            # Update counter AFTER actual network write succeeds
            progress["sent"] += raw_len
        else:
            msg_type, payload = item
            send_frame(conn, msg_type, payload)

        send_queue.task_done()


def send_file(conn, key: bytes, path: str):
    TUNER.begin_transfer()
    session = TUNER.session_id
    sha = hashlib.sha256()
    filename = os.path.basename(path)
    total_size = os.path.getsize(path)

    # Shared progress dictionary updated by network_sender
    progress = {"sent": 0}

    max_inflight = max(1, os.cpu_count() // 2 + 1)

    send_frame(
        conn, "File", f"META:{session}:{filename}:{total_size}".encode("utf-8")
    )

    pending = deque()  # holds Futures in submission order

    start_time = time.time()
    last_update = start_time

    def print_progress():
        nonlocal last_update
        now = time.time()
        if now - last_update >= 0.2:  # Update UI/terminal ~5 times per second
            current_sent = progress["sent"]
            elapsed = now - start_time
            if current_sent > total_size:
                current_sent = total_size

            speed = current_sent / elapsed if elapsed > 0 else 0
            remaining = total_size - current_sent
            eta = remaining / speed if speed > 0 else 0
            percent = (
                (current_sent / total_size) * 100 if total_size > 0 else 100.0
            )
            speed_mb = speed / (1024 * 1024)
            eta_min, eta_sec = int(eta // 60), int(eta % 60)

            print(
                f"\rSent {current_sent/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB "
                f"({percent:.1f}%) | {speed_mb:.1f} MB/s | ETA {eta_min:02}:{eta_sec:02}",
                end="",
            )
            last_update = now

    with open(path, "rb") as f:
        eof = False

        while not eof or pending:
            # ── Fill the pipeline up to max_inflight ─────────────────────────
            while not eof and len(pending) < max_inflight:
                chunk = f.read(TUNER.chunk_size)
                if not chunk:
                    eof = True
                    break
                sha.update(chunk)
                # Store (future, raw_chunk_length)
                pending.append((en.parallel_encrypt(key, chunk), len(chunk)))

            # ── Drain the oldest completed future into the send queue ─────────
            if pending:
                future, raw_len = pending.popleft()
                encrypted = future.result()  # blocks only if not ready

                # Push tuple with raw size and progress handle
                send_queue.put(("File", encrypted, raw_len, progress))

                print_progress()

    # ── Wait & print progress while network_sender flushes chunks over wire ──
    while progress["sent"] < total_size:
        print_progress()
        time.sleep(0.05)

    # Final guarantee queue is completely empty
    send_queue.join()

    # Final 100% display update
    print_progress()

    # ── Send FILE_END and FILE_HASH directly ─────────────────────────────────
    send_system(conn, "FILE_END")
    send_system(conn, f"FILE_HASH:{sha.hexdigest()}")

    TUNER.end_transfer()
    print(f"\n[file sent: {filename}]")
    
# 1. Create a dedicated queue for the background file worker
file_processing_queue = Queue(maxsize=128)

def file_worker_thread(key: bytes):
    """This thread does all the heavy lifting off the network loop"""
    file_handle = None
    sha = hashlib.sha256()
    received_bytes = 0
    current_file = None
    local_hash = None

    while True:
        task = file_processing_queue.get()
        if task is None:
            break
        
        action, payload = task
        
        if action == "META":
            meta = payload.decode("utf-8")
            _, _, current_file,total_bytes = meta.split(":", 3)
            total_bytes=int(total_bytes )
            path = os.path.join("received_files", current_file)
            file_handle = open(path, "wb")
            received_bytes = 0
            sha = hashlib.sha256()
            
        elif action == "CHUNK":
            if file_handle:
                decrypted_chunk = payload.result() 
                file_handle.write(decrypted_chunk)
                sha.update(decrypted_chunk)
                received_bytes += len(decrypted_chunk)
                pct = (received_bytes / total_bytes) * 100 if total_bytes else 0
                print(f"\rReceived {received_bytes/(1024*1024):.1f}/{total_bytes/(1024*1024):.1f} MB ({pct:.1f}%)", end='')
                
        elif action == "END":
            local_hash = sha.hexdigest()
            if file_handle:
                file_handle.close()
                print(f"\nFile received: {current_file}")
                
        elif action == "HASH":
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            sender_hash = payload.split(":", 1)[1]
            if local_hash and sender_hash == local_hash:
                print("-> File Verified")
            else:
                print("-> File corrupted")
            local_hash = None
            
        file_processing_queue.task_done()

def run_chat(conn, username):
    global conn_alive
    os.makedirs("received_files", exist_ok=True)

    print("[*] Exchanging public keys & authenticating...")

    # Auth Check - Aborts if untrusted or tampered
    try:
        key, safety_code = handshake_auth(conn)
        print(f"[SECURE] Key Verified! Safety Code: {safety_code}")
    except Exception as e:
        print(f"\n[ABORTED] Security verification failed: {e}")
        conn.close()
        return
    
    send_system(conn, f"JOIN:{username}")
    t = threading.Thread(target=receiver_loop, args=(conn, key,), daemon=True)
    net_thread = threading.Thread(target=network_sender, args=(conn,), daemon=True)
    net_thread.start()
    t.start()
    worker = threading.Thread(target=file_worker_thread, args=(key,), daemon=True)
    worker.start()
    send_system(conn, "READY")
    if not ready_event.wait(timeout=8):
        print("[WARN] peer ready timeout") 
    recv_ready.wait(timeout=2)
    TUNER.auto_tune(conn, send_system, send_queue)
    print(f"[AutoTune] {TUNER.status()}")
    sender_loop(conn, username, key)

def receiver_loop(conn, key: bytes):
    global conn_alive
    exp_file = False
    name = None
    recv_ready.set()

    try:
        while True:
            header = transport.read_exactly(conn, 5)
            t = protocol.d_type(header[0:1])
            l = protocol.d_length(header[1:5])
            payload = transport.read_exactly(conn, l)

            if t == 1:
                txt = en.decrypt_msg(key, payload).decode("utf-8")
                print(f"{name}:", txt)
                
            elif t == 2:
                payload = payload.decode("utf-8")
                if payload.startswith("JOIN:"):             # User joined
                    name = payload[5:]
                    print(f"[{name} joined]")
                elif payload.startswith("LEAVE:"):          # User left
                    name = payload[6:]
                    print(f"[{name} left]")
                    break
                elif payload == "READY":
                    ready_event.set()
                elif payload.startswith("TUNE"):
                    _, mode, chunk, queue = payload.split()
                    TUNER.chunk_size = int(chunk)
                    TUNER.queue_size = int(queue)
                    TUNER.mode = mode
                elif payload == "PING":                         # Pinging to new user for TUNER
                    send_system(conn, "PONG")
                elif payload == "PONG":                         # returning ping to check timing
                    TUNER.handle_pong()
                    
                # -- THE FIX: Send system file messages to the worker queue --
                elif payload == "FILE_END":
                    file_processing_queue.put(("END", None))
                    exp_file = False
                elif payload.startswith("FILE_HASH:"):
                    file_processing_queue.put(("HASH", payload))
                # -----------------------------------------------------------
                
            elif t == 3:
                if not exp_file:
                    if payload.startswith(b"META:"):
                        file_processing_queue.put(("META", payload))
                        exp_file = True
                else:
                    future = recv_pool.submit(en.decrypt_msg, key, payload)
                    file_processing_queue.put(("CHUNK", future))
                    
    except Exception as e:
        conn_alive = False
        if exp_file: # We don't have file_handle here anymore, just print interruption
            print("\nFile transfer interrupted")
        print("receiver stopped:", e)

def sender_loop(conn, username, key: bytes):
    global conn_alive
    global send_queue
    
    try:
        while conn_alive:
            txt = input("You: ").strip()
            if txt == "/quit":
                send_system(conn, f"LEAVE:{username}")
                en.shutdown_pool()
                send_queue.put(None)
                conn.close()
                break
            elif txt.startswith("/send "):
                path = txt[6:].strip()
                if not os.path.isfile(path):
                    print("File not found")
                    continue
                send_file(conn, key, path)
                continue
            elif txt.startswith("/mode "):
                parts = txt.split(" ", maxsplit=1)
                if len(parts) == 1 or parts[1] == "status":
                    print(TUNER.status())
                    continue
                success, msg = TUNER.apply_mode(parts[1].lower())
                if success:
                    set_mode(parts[1].title())
                print(msg)
                send_queue.maxsize = TUNER.queue_size
                continue

            payload = en.encrypt_msg(key, txt.encode("utf-8"))
            send_frame(conn, "Text", payload)

    except (ConnectionResetError, BrokenPipeError):
        conn_alive = False
        print(f"{username} disconnected!")

# if __name__ == "__main__":
