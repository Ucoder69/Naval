from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import hashlib

def derive_key(password: str):
    return hashlib.sha256(password.encode()).digest()

class AESGCMCipher:
    def __init__(self, key: bytes):
        self.aesgcm= AESGCM(key)
        self.base_nonce=os.urandom(8)
        self.counter=0
        
    def encrypt(self, data:bytes)-> bytes:
        nonce=self.base_nonce+ self.counter.to_bytes(4, "big")
        self.counter+=1
        ciphertext=self.aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext
    
    def decrypt(self, data: bytes)->bytes:
        nonce=data[:12]
        ciphertext=data[12:]
        return self.aesgcm.decrypt(nonce, ciphertext, None)       