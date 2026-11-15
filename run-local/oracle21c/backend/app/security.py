"""Security: password hashing (bcrypt), JWT tokens and role-based access checks."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import oracledb
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import settings
from .database import get_db, query_one

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

USER_COLUMNS = "user_id AS id, full_name AS name, email, user_role AS role, phone, address"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user["id"]), "role": user["role"], "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme), db: oracledb.Connection = Depends(get_db)) -> dict:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                                 headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = query_one(db, f"SELECT {USER_COLUMNS} FROM app_users WHERE user_id = :id", {"id": user_id})
    if user is None:
        raise unauthorized
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
