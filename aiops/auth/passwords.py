from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False
