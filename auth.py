import hashlib
import hmac
import secrets


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 310000
    )
    return f"{salt}${digest.hex()}"


def verify_password(password, encoded):
    try:
        salt, expected = encoded.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), 310000
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def authenticate(username, password, db_path):
    from db import connect

    with connect(db_path) as connection:
        user = connection.execute(
            "SELECT id, username, full_name, password_hash, role FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return {key: user[key] for key in ("id", "username", "full_name", "role")}
