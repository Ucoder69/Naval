
tyPe_={"Text": 1, "Image":2 , "File": 3}
max_length= 65538

def e_type(s):
    tyPe={"Text": 1, "System" :2 ,"File":3}
    if s in tyPe:
        tn=tyPe[s]
        bt=tn.to_bytes(1, byteorder="big")
        return bt
    else:
        raise ValueError("Unknown name Written")
    
def e_length(n :int):
    if 0<= n <= 0xffffffff:     #32 bits:0xffffffff
        bl=n.to_bytes(4, byteorder="big")
        return bl
    else:
        raise ValueError("payload length out of range")
        
def d_type(bt):
    s=int.from_bytes(bt, byteorder="big")
    return s

def d_length(bl):
    n=int.from_bytes(bl, byteorder="big")
    return n

if __name__ == "__main__":
    msg_type = "Text"
    payload = b"hello"

    header = e_type(msg_type) + e_length(len(payload))
    print("Encoded header:", header)

    t = d_type(header[0:1])
    l = d_length(header[1:5])

    print("Decoded type:", t)
    print("Decoded length:", l)
    
