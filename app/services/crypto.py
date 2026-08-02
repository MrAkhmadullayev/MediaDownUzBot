import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken


class FieldCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Shifrlangan ma'lumotni o'qib bo'lmadi") from exc


def create_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode(), usedforsecurity=True).hexdigest()


def csrf_token(session_token: str, secret_key: str) -> str:
    return hmac.new(
        secret_key.encode(),
        session_token.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


def tokens_match(first: str, second: str) -> bool:
    return hmac.compare_digest(first, second)
