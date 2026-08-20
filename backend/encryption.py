from concurrent.futures import ThreadPoolExecutor
import nacl.bindings
import nacl.pwhash
import nacl.utils

# Fixed 16-byte application domain salt (No network salt exchange needed!)
APP_SALT = b"Naval_LAN_App_v1"


def derive_key(password: str) -> bytes:
    """Derives a 32-byte key using Argon2id.

    Takes ~50-100ms on mobile, blocking GPU/ASIC brute-force cracking.
    """
    return nacl.pwhash.argon2id.kdf(
        size=32,
        password=password.encode("utf-8"),
        salt=APP_SALT,
        opslimit=nacl.pwhash.argon2id.OPSLIMIT_MODERATE,
        memlimit=nacl.pwhash.argon2id.MEMLIMIT_MODERATE,
    )


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
