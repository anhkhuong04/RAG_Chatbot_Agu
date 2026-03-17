import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# Admin credentials (from env or defaults)
# ---------------------------------------------------------------------------
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "Admin")
_raw_password: str = os.getenv("ADMIN_PASSWORD", "123456")
ADMIN_HASHED_PASSWORD: str = hash_password(_raw_password)

# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------
_default_secret = secrets.token_urlsafe(64)
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", _default_secret)
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "1"))

if JWT_SECRET_KEY == _default_secret:
    logger.warning(
        "⚠️  JWT_SECRET_KEY not set — using a random key. "
        "Tokens will be invalidated on every server restart. "
        "Set JWT_SECRET_KEY in your .env for persistence."
    )


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=JWT_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI dependency — protects admin routes
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise JWTError("Missing subject claim")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
