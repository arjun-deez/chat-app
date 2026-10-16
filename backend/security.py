import asyncio
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException

SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")


async def hash_password(password: str) -> bytes:
    # slow on purpose, so run it off the main event loop
    def _hash():
        salt = secrets.token_bytes(16)
        return salt + hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return await asyncio.to_thread(_hash)


async def check_password(password: str, hashed: bytes) -> bool:
    def _check():
        salt, key = hashed[:16], hashed[16:]
        new = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(key, new)
    return await asyncio.to_thread(_check)


def make_token(user_id: str, username: str) -> str:
    payload = {
        "id": user_id,
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def read_token(token: str) -> dict:
    """Returns {"id", "username", ...} or raises jwt.PyJWTError."""
    return jwt.decode(token, SECRET, algorithms=["HS256"])


def current_user(authorization: str = Header(None)) -> dict:
    """FastAPI dependency: use it on any route that needs a logged-in user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in")
    try:
        return read_token(authorization[7:])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired, please log in again")
