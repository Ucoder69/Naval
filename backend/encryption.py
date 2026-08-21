from concurrent.futures import ThreadPoolExecutor
import hashlib
import nacl.bindings
import nacl.pwhash
import nacl.utils
import nacl.public
# Fixed 16-byte application domain salt (No network salt exchange needed!)
# APP_SALT = b"Naval_LAN_App_v1"

def generate_keypair():
    """Generates an ephemeral Curve25519 Private/Public keypair."""
    sk = nacl.public.PrivateKey.generate()
    return sk, sk.public_key


def derive_shared_key(
    my_sk: nacl.public.PrivateKey, peer_pk_bytes: bytes
) -> bytes:
    """Derives the 32-byte shared symmetric key using ECDH."""
    peer_pk = nacl.public.PublicKey(peer_pk_bytes)
    return nacl.bindings.crypto_box_beforenm(peer_pk.encode(), my_sk.encode())


def generate_safety_number(my_pk_bytes: bytes, peer_pk_bytes: bytes) -> str:
    """Generates a deterministic 6-digit WhatsApp-style safety number."""
    combined = b"".join(sorted([bytes(my_pk_bytes), bytes(peer_pk_bytes)]))
    digest = hashlib.sha256(combined).hexdigest()
    safety_code = str(int(digest[:8], 16) % 1000000).zfill(6)
    return f"{safety_code[:3]}-{safety_code[3:]}"

class XChaCha20Cipher:

    def __init__(self, key: bytes):
        self.key = bytes(key)

    def encrypt(self, data: bytes) -> bytes:
        data_bytes = bytes(data)
        nonce = nacl.utils.random(24)
        ciphertext = nacl.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            message=data_bytes,
            aad=b"",
            nonce=nonce,
            key=self.key,
        )
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        data_bytes = bytes(data)

        if len(data_bytes) < 40:  # 24B nonce + 16B Poly1305 tag minimum
            raise ValueError("Payload too short to be encrypted")

        nonce = data_bytes[:24]
        ciphertext = data_bytes[24:]

        try:
            return nacl.bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(
                ciphertext=ciphertext,
                aad=b"",
                nonce=nonce,
                key=self.key,
            )
        except nacl.exceptions.CryptoError:
            print(
                "\n[ERROR] Decryption Failed: Wrong password or corrupted payload!"
            )
            raise

# Alias so your main app imports won't break if AESGCMCipher is referenced elsewhere
AESGCMCipher = XChaCha20Cipher


# --- Standalone Helper Functions ---


def encrypt_msg(key: bytes, data: bytes) -> bytes:
    """Encrypt a chat message or standalone data block."""
    cipher = XChaCha20Cipher(key)
    return cipher.encrypt(data)


def decrypt_msg(key: bytes, data: bytes) -> bytes:
    """Decrypt any incoming payload regardless of origin."""
    cipher = XChaCha20Cipher(key)
    return cipher.decrypt(data)


def encrypt_chunk(key: bytes, chunk: bytes) -> bytes:
    """Encrypt one file chunk."""
    return encrypt_msg(key, chunk)


# --- Thread Pool ---
# Worker threads release GIL in Libsodium C code for high CPU performance
_pool = ThreadPoolExecutor(max_workers=2)


def parallel_encrypt(key: bytes, chunk: bytes):
    """Submit one chunk to the pool. Returns a Future[bytes]."""
    return _pool.submit(encrypt_chunk, key, chunk)


def shutdown_pool():
    """Call once on app exit to clean up worker threads."""
    _pool.shutdown(wait=False)
