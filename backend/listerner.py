import socket
import protocol

def read_exactly(conn, n):
    a=0
    b=[]
    while a<n:
        remaining=n-a
        data=conn.recv(min(1024, remaining))
        if len(data)==0:
            raise ConnectionError
        a+=len(data)
        b.append(data)
    c=b"".join(b)
    assert len(data)==n
    return c

def read(read_exactly):
    try:
        while True:    
            try:
                header=read_exactly(conn, 3)
            except ConnectionError:
                print("Connection closed!")
                break
        
            t= protocol.d_type(header[0:1])  
            l= protocol.d_length(header[1:3])  
            payload = read_exactly(conn, l) 
            if t==1:
                txt=payload.decode("utf-8")
                print("Peer:", txt)
    except Exception:
        print("receiver stopped")


def host(port):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.bind(("192.168.29.147", port))

    s.listen(1)
    print("Listening...")

    conn, addr =s.accept()
    print("connected from", addr)
    return conn

port=5000
conn=host(port)
read(read_exactly)