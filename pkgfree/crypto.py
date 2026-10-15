"""Cryptographic primitives used by PS4 fake PKGs."""

import hashlib
import hmac
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import keys

XTS_SECTOR_SIZE = 0x1000


class CryptoError(Exception):
    pass


def _rsa_decrypt_pkcs1v15(ciphertext: bytes, n: int, d: int) -> bytes:
    """Raw RSA decryption followed by PKCS#1 v1.5 (type 2) unpadding."""
    c = int.from_bytes(ciphertext, "big")
    if c >= n:
        raise CryptoError("RSA ciphertext out of range")
    em = pow(c, d, n).to_bytes(256, "big")
    if em[0] != 0 or em[1] != 2:
        raise CryptoError("RSA padding non valido (PKG retail o chiave errata)")
    sep = em.find(b"\x00", 2)
    if sep < 10:
        raise CryptoError("RSA padding non valido (PKG retail o chiave errata)")
    return em[sep + 1:]


def decrypt_dk3(ciphertext: bytes) -> bytes:
    return _rsa_decrypt_pkcs1v15(ciphertext, keys.PKG_DERIVED_KEY3_N, keys.PKG_DERIVED_KEY3_D)[:32]


def decrypt_ekpfs(ciphertext: bytes) -> bytes:
    return _rsa_decrypt_pkcs1v15(ciphertext, keys.FAKE_N, keys.FAKE_D)[:32]


def entry_iv_key(entry_raw: bytes, dk3: bytes) -> bytes:
    """SHA-256 over the 32-byte table entry followed by DK3: first 16 bytes IV, last 16 key."""
    return hashlib.sha256(entry_raw + dk3).digest()


def aes_cbc_decrypt(iv_key: bytes, data: bytes) -> bytes:
    usable = len(data) - (len(data) % 16)
    dec = Cipher(algorithms.AES(iv_key[16:32]), modes.CBC(iv_key[:16])).decryptor()
    return dec.update(data[:usable]) + dec.finalize() + data[usable:]


def pfs_gen_crypto_key(ekpfs: bytes, seed: bytes, new_crypt: bool = False) -> tuple[bytes, bytes]:
    """Derive the (data_key, tweak_key) pair of the PFS image."""
    if new_crypt:
        ekpfs = hmac.new(ekpfs, seed, hashlib.sha256).digest()
    digest = hmac.new(ekpfs, struct.pack("<I", 1) + seed, hashlib.sha256).digest()
    tweak_key, data_key = digest[:16], digest[16:32]
    return data_key, tweak_key


class XtsDecryptor:
    """AES-128-XTS with 0x1000-byte sectors, as used by encrypted PFS images."""

    def __init__(self, data_key: bytes, tweak_key: bytes):
        self._key = algorithms.AES(data_key + tweak_key)

    def decrypt(self, data: bytes, first_sector: int) -> bytes:
        if len(data) % XTS_SECTOR_SIZE:
            raise CryptoError("XTS data must be sector aligned")
        out = bytearray(len(data))
        view = memoryview(data)
        for i in range(0, len(data), XTS_SECTOR_SIZE):
            tweak = (first_sector + i // XTS_SECTOR_SIZE).to_bytes(16, "little")
            dec = Cipher(self._key, modes.XTS(tweak)).decryptor()
            out[i:i + XTS_SECTOR_SIZE] = dec.update(view[i:i + XTS_SECTOR_SIZE])
        return bytes(out)
