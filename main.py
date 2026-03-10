from backend.server import server
from backend.client import client
from backend.config import set_username, get_username

def main():
    username=get_username()
    if username:
        print("Press:\n1. Host\n2. Connect\n3. Rename")
        choice=int(input("Enter the what you want to do: "))
        if choice==1:
            server(get_username())
        elif choice==2:
            client(get_username())
        elif choice==3:
            new_username=input("Enter your NEW username")
            set_username(new_username)
            main()
    else:
        print("Press:\n1. Host\n2. Connect")
        choice=int(input("Enter the what you want to do: "))
        if choice==1:
            username=input("Enter your username: ").strip()
            set_username(username)
            server(username)
        else:
            username=input("Enter your username: ").strip()
            set_username(username)
            client(username)
            
if __name__=="__main__":
    main()
    