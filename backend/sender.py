import socket
import protocol

def connect(port):
    s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    s.connect(("192.168.29.147", port))
    return s

def send(s):
    try:
        while True:
            txt=input("You:")
            payload=txt.encode("utf-8")
            header=protocol.e_type("Text")+ protocol.e_length(len(payload))
        
            s.sendall(header)
            s.sendall(payload)
    except KeyboardInterrupt:#added later
        print("\nYOU ended the chat!")
    except ConnectionResetError:#added later
        print("They ended chat!")
port=5000
s = connect(port)
send(s)