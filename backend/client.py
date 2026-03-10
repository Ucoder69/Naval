import socket
from zeroconf import ServiceBrowser, Zeroconf,ServiceListener
from backend.config import get_username
from backend.app import run_chat
import time 

peers={} #username: (ip,port)
class NavalListener(ServiceListener):
    def add_service(self, zeroconf, service_type, name):
        # global peers
        info= zeroconf.get_service_info(service_type, name)
        if not info or not info.addresses:
            return
        ip=socket.inet_ntoa(info.addresses[0])
        port= info.port
        user= info.properties.get(b"user", b"").decode()
        peers[user]=(ip,port)
        print(f"Found {user} @ {ip}: {port}")
    def remove_service(self, zeroconf,service_type,name):
        pass
    def update_services(self, zeroconf, service_type, name):
        pass    
def browse_mdns():
    zeroconf=Zeroconf()
    listener= NavalListener()
    ServiceBrowser(zeroconf, "_naval._tcp.local.", listener) 
    return zeroconf

def get_local_ip():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()
        
def client(user):
    # user=get_username()
    zeroconf=browse_mdns()
    print("Searching for servers...")
    time.sleep(2)
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    choice=input("Connect to (username) or press Enter for manual: \n").strip()
    if choice and choice in peers:
        ip, port=peers[choice]
    else:
        ip=ip=get_local_ip()
        port=int(input("PORT:"))

    s.connect((ip, port))
    zeroconf.close()
    run_chat(s, user)


if __name__=="__main__":
    client()