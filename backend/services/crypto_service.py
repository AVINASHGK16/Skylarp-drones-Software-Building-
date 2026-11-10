"""
Cryptographic, Encryption and Token Security Service.

Provides:
1. AES-256-GCM Envelope Encryption for third-party credentials.
2. Salted PBKDF2-HMAC-SHA256 Password Hashing.
3. Tenant-Scoped JWT Authentication Tokens.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
import uuid
from typing import Any
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Secret keys resolved from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "skylarp-dev-jwt-secret-do-not-use-in-production-12345678")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))  # 24 hours

MASTER_KEY_RAW = os.getenv("ENCRYPTION_MASTER_KEY", "skylarp-master-key-32-bytes-long!")
# Ensure master key is exactly 32 bytes for AES-256
ENCRYPTION_KEY = hashlib.sha256(MASTER_KEY_RAW.encode("utf-8")).digest()


# =====================================================================
# 1. AES-256-GCM Credential Encryption
# =====================================================================

def encrypt_credentials(plaintext: str, key_id: str = "v1") -> str:
    """
    Encrypt sensitive credentials using authenticated AES-256-GCM.
    Returns: aes_gcm:<key_id>:<hex_nonce>:<hex_ciphertext>
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty credentials")
    
    aesgcm = AESGCM(ENCRYPTION_KEY)
    nonce = secrets.token_bytes(12)  # Standard 96-bit nonce for GCM
    data = plaintext.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, data, associated_data=key_id.encode("utf-8"))
    
    return f"aes_gcm:{key_id}:{nonce.hex()}:{ciphertext.hex()}"


def decrypt_credentials(encrypted_payload: str) -> str:
    """
    Decrypt credentials stored in aes_gcm format.
    Raises ValueError if payload format is invalid or tampering is detected.
    """
    if not encrypted_payload or not encrypted_payload.startswith("aes_gcm:"):
        raise ValueError("Invalid encrypted payload format")
    
    parts = encrypted_payload.split(":")
    if len(parts) != 4:
        raise ValueError("Malformed encrypted payload")
    
    _, key_id, nonce_hex, ciphertext_hex = parts
    nonce = bytes.fromhex(nonce_hex)
    ciphertext = bytes.fromhex(ciphertext_hex)
    
    aesgcm = AESGCM(ENCRYPTION_KEY)
    try:
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=key_id.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to decrypt credentials (authentication tag mismatch or invalid key): {e}") from e


# =====================================================================
# 2. Salted PBKDF2-HMAC-SHA256 Password Security
# =====================================================================

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 600,000 iterations and random salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash using constant-time comparison."""
    if not plain_password or not hashed_password:
        return False
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = bytes.fromhex(parts[3])
        
        computed_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(expected_hash, computed_hash)
    except Exception:
        return False


# =====================================================================
# 3. Tenant-Scoped JWT Authentication Tokens
# =====================================================================

def create_access_token(
    user_id: uuid.UUID,
    email: str,
    tenant_id: uuid.UUID | None = None,
    role: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token with user and optional tenant claims."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=JWT_EXPIRATION_MINUTES))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email.lower(),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if tenant_id:
        payload["tenant_id"] = str(tenant_id)
    if role:
        payload["role"] = role
        
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise ValueError("Token has expired") from e
    except jwt.PyJWTError as e:
        raise ValueError("Invalid authentication token") from e

