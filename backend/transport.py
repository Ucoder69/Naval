import socket

def read_exactly(conn, n):
    # 1. Allocate the exact size once
    buffer = bytearray(n)
    view = memoryview(buffer)
    
    a = 0
    while a < n:
        # 3. recv_into grabs whatever the OS has ready (up to the remaining amount)
        # No 64KB limit. If the OS has 2MB ready, it grabs 2MB in one microsecond.
        chunk_size = conn.recv_into(view[a:], n - a)
        if chunk_size == 0:
            raise ConnectionError("Connection closed abruptly")
        a += chunk_size
        
    # Convert to standard bytes for decryption
    return buffer
