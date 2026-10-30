import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet
from app.config import settings

logger = logging.getLogger("healthslip.encryption")

class EncryptionService:
    """
    Encryption at Rest Service for Patient Sensitive Identifiers (India DPDP Act 2023 / HIPAA).
    Uses AES-128-CBC with HMAC authentication (Fernet standard).
    """
    _fernet: Optional[Fernet] = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        if cls._fernet is None:
            # Derive deterministic, urlsafe 32-byte base64 Fernet key from secret or explicit key
            raw_key_material = (settings.DATA_ENCRYPTION_KEY or settings.SECRET_KEY).encode("utf-8")
            derived_32bytes = hashlib.sha256(raw_key_material).digest()
            fernet_key = base64.urlsafe_b64encode(derived_32bytes)
            cls._fernet = Fernet(fernet_key)
        return cls._fernet

    @classmethod
    def encrypt(cls, plain_text: Optional[str]) -> Optional[str]:
        """Encrypt sensitive plaintext string with prefix 'enc$'"""
        if not plain_text:
            return plain_text
        try:
            f = cls._get_fernet()
            encrypted_bytes = f.encrypt(plain_text.strip().encode("utf-8"))
            return f"enc${encrypted_bytes.decode('utf-8')}"
        except Exception as e:
            logger.error(f"[Encryption] Error encrypting field: {e}")
            return plain_text

    @classmethod
    def decrypt(cls, cipher_text: Optional[str]) -> Optional[str]:
        """Decrypt string if prefixed with 'enc$', otherwise return raw for backward compatibility"""
        if not cipher_text:
            return cipher_text
        if not cipher_text.startswith("enc$"):
            return cipher_text # Backward compatible with existing unencrypted rows
        try:
            f = cls._get_fernet()
            raw_token = cipher_text[4:].encode("utf-8")
            decrypted_bytes = f.decrypt(raw_token)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"[Encryption] Decryption failed: {e}")
            return cipher_text
