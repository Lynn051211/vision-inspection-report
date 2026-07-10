"""AES-256-CBC 加密工具 — API Key 安全存储"""

import os
import base64
import secrets
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _derive_key(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """从密码派生 AES-256 密钥"""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000, dklen=32)
    return key, salt


def encrypt(plaintext: str, password: str) -> str:
    """AES-256-CBC 加密，返回 base64(salt + iv + ciphertext)"""
    key, salt = _derive_key(password)
    iv = secrets.token_bytes(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))

    # PKCS7 padding
    data = plaintext.encode()
    pad_len = 16 - (len(data) % 16)
    data += bytes([pad_len] * pad_len)

    encryptor = cipher.encryptor()
    ct = encryptor.update(data) + encryptor.finalize()

    return base64.b64encode(salt + iv + ct).decode()


def decrypt(ciphertext: str, password: str) -> str:
    """AES-256-CBC 解密"""
    raw = base64.b64decode(ciphertext)
    salt, iv, ct = raw[:16], raw[16:32], raw[32:]

    key, _ = _derive_key(password, salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    pt = decryptor.update(ct) + decryptor.finalize()

    # 移除 PKCS7 padding
    pad_len = pt[-1]
    return pt[:-pad_len].decode()


def mask_api_key(key: str) -> str:
    """脱敏显示：sk-aB3x...xYz1"""
    if len(key) <= 12:
        return "*" * len(key)
    return key[:7] + "●●●●" + key[-4:]
