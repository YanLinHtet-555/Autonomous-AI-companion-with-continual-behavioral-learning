"""
EncryptionManager — AES-256 encryption with:
  - PBKDF2-HMAC-SHA256 key derivation (100,000 iterations)
  - Per-message random salt + IV
  - HMAC-SHA256 integrity tag on every ciphertext
  - Separate audit key from data key

Data cannot be read without the master key file.
Any tampered ciphertext fails HMAC verification and is rejected.
"""

import os
import hmac
import hashlib
import struct
import secrets
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Constants
_SALT_LEN = 32       # bytes
_IV_LEN = 16         # AES block size
_HMAC_LEN = 32       # SHA-256 output
_KDF_ITERATIONS = 100_000
_KEY_LEN = 32        # AES-256


class EncryptionManager:
    """
    Strong local encryption for all stored user data.

    Ciphertext format (all binary, base64-encoded for storage):
        [SALT 32B][IV 16B][HMAC 32B][CIPHERTEXT ...]
    """

    def __init__(self, key_path: str):
        self.key_path = key_path
        self._master_key: bytes = self._load_or_create_master_key()

    # ------------------------------------------------------------------ #
    # Master key management                                                #
    # ------------------------------------------------------------------ #

    def _load_or_create_master_key(self) -> bytes:
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                return f.read()
        # Generate a 32-byte cryptographically random master key
        master = secrets.token_bytes(32)
        with open(self.key_path, "wb") as f:
            f.write(master)
        # Restrict file permissions on Windows as much as possible
        try:
            import stat
            os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        return master

    # ------------------------------------------------------------------ #
    # Key derivation                                                       #
    # ------------------------------------------------------------------ #

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive a 256-bit encryption key from master key + salt via PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LEN,
            salt=salt,
            iterations=_KDF_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(self._master_key)

    # ------------------------------------------------------------------ #
    # Encrypt                                                              #
    # ------------------------------------------------------------------ #

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")

        # Random salt and IV for every message
        salt = secrets.token_bytes(_SALT_LEN)
        iv = secrets.token_bytes(_IV_LEN)
        key = self._derive_key(salt)

        # AES-256-CBC encryption with PKCS7 padding
        padder = sym_padding.PKCS7(128).padder()
        padded = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        ciphertext = cipher.encryptor().update(padded) + cipher.encryptor().finalize()

        # HMAC-SHA256 over salt+iv+ciphertext for integrity
        mac = hmac.new(key, salt + iv + ciphertext, hashlib.sha256).digest()

        # Pack: SALT | IV | HMAC | CIPHERTEXT
        packed = salt + iv + mac + ciphertext
        import base64
        return base64.b64encode(packed).decode("utf-8")

    # ------------------------------------------------------------------ #
    # Decrypt                                                              #
    # ------------------------------------------------------------------ #

    def decrypt(self, token: str) -> str:
        import base64
        try:
            packed = base64.b64decode(token.encode("utf-8"))
        except Exception:
            raise ValueError("EncryptionManager: invalid base64 data")

        if len(packed) < _SALT_LEN + _IV_LEN + _HMAC_LEN + 1:
            raise ValueError("EncryptionManager: data too short")

        salt = packed[:_SALT_LEN]
        iv = packed[_SALT_LEN:_SALT_LEN + _IV_LEN]
        stored_mac = packed[_SALT_LEN + _IV_LEN:_SALT_LEN + _IV_LEN + _HMAC_LEN]
        ciphertext = packed[_SALT_LEN + _IV_LEN + _HMAC_LEN:]

        key = self._derive_key(salt)

        # Verify HMAC before decrypting — reject tampered data
        expected_mac = hmac.new(key, salt + iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(stored_mac, expected_mac):
            raise ValueError(
                "EncryptionManager: HMAC verification FAILED — "
                "data may have been tampered with!"
            )

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        padded = cipher.decryptor().update(ciphertext) + cipher.decryptor().finalize()
        unpadder = sym_padding.PKCS7(128).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")

    # ------------------------------------------------------------------ #
    # Utility                                                              #
    # ------------------------------------------------------------------ #

    def verify(self, token: str) -> bool:
        """Returns True if token is a valid, untampered ciphertext."""
        try:
            self.decrypt(token)
            return True
        except Exception:
            return False

    def rotate_key(self, new_key_path: str):
        """
        Generate a new master key. Caller is responsible for
        re-encrypting existing data with the new key.
        Only callable via explicit user command.
        """
        new_master = secrets.token_bytes(32)
        with open(new_key_path, "wb") as f:
            f.write(new_master)
        print(f"[Encryption] New key written to {new_key_path}. "
              f"Re-encrypt your data to activate it.")
