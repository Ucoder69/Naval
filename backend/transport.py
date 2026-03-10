import socket

def read_exactly(conn, n):
    a=0
    b=[]
    while a<n:
        remaining=n-a
        data=conn.recv(min(65530, remaining))
        if len(data)==0:
            raise ConnectionError
        a+=len(data)
        b.append(data)
    c=b"".join(b)
    return c