"""Security: password hashing, login sessions in an HttpOnly cookie, CSRF check and
permission checks (role-based access control from the PROFILES / AUTHORIZATIONS tables).

How a request is authenticated:
  1. After login the server sets the cookie  ims_session=<signed JWT>; HttpOnly; Secure; SameSite=Strict; Path=/api
       HttpOnly  -> JavaScript in the page can't read it, so an XSS bug can't steal the session
       Secure    -> only sent over HTTPS (http://localhost counts as secure for development)
       SameSite  -> the browser doesn't send it with requests started by other websites (CSRF protection)
  2. The browser sends the cookie automatically with every /api request.
  3. Requests that change data must also carry the header  X-Requested-With: XMLHttpRequest
     (our Angular app adds it). Other websites can't add that header to a cross-site request
     without permission, so this is a second CSRF guard.
  4. For tools such as Swagger /docs, "Authorization: Bearer <token>" works as well.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import oracledb
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer

from .config import settings
from .database import get_db, query, query_one


class Perm:
    """Permission codes, the same as the PERMISSIONS table (01_schema.sql)."""
    CATALOG_READ = "CATALOG_READ"
    CATALOG_WRITE = "CATALOG_WRITE"
    ORDER_PLACE = "ORDER_PLACE"
    ORDER_READ_OWN = "ORDER_READ_OWN"
    ORDER_READ_ALL = "ORDER_READ_ALL"
    ORDER_MANAGE = "ORDER_MANAGE"
    STOCK_READ = "STOCK_READ"
    STOCK_WRITE = "STOCK_WRITE"
    REPORT_VIEW = "REPORT_VIEW"
    REPORT_DOWNLOAD = "REPORT_DOWNLOAD"
    USER_READ = "USER_READ"
    USER_MANAGE = "USER_MANAGE"


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# "Authorize" button in Swagger /docs: logs in through /api/auth/token and sends a Bearer token.
bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(settings.cookie_name, create_access_token(user_id),
                        max_age=settings.access_token_minutes * 60, path="/api",
                        httponly=True, secure=settings.cookie_secure, samesite="strict")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.cookie_name, path="/api", httponly=True,
                           secure=settings.cookie_secure, samesite="strict")


def load_user(db: oracledb.Connection, user_id: int) -> dict | None:
    """The user with their profiles and the permissions those profiles grant."""
    user = query_one(db, """
        SELECT u.user_id AS id, u.full_name AS name, u.email, u.account_status,
               cp.phone, cp.address_line, cp.city, cp.state, cp.pincode, cp.preferred_outlet_id
          FROM users u LEFT JOIN customer_profiles cp ON cp.customer_id = u.user_id
         WHERE u.user_id = :id""", {"id": user_id})
    if user is None:
        return None
    profiles = query(db, """
        SELECT p.profile_code, p.is_staff FROM user_profiles up JOIN profiles p ON p.profile_id = up.profile_id
         WHERE up.user_id = :id ORDER BY p.profile_id""", {"id": user_id})
    perms = query(db, "SELECT DISTINCT permission_code FROM v_user_access WHERE user_id = :id", {"id": user_id})
    user["profiles"] = [p["profile_code"] for p in profiles]
    user["permissions"] = sorted(p["permission_code"] for p in perms)
    user["is_staff"] = any(p["is_staff"] for p in profiles)
    # A simple label for the UI: ADMIN, STAFF or CUSTOMER
    user["role"] = "ADMIN" if "ADMIN" in user["profiles"] else "STAFF" if user["is_staff"] else "CUSTOMER"
    return user


def get_current_user(request: Request, bearer_token: str | None = Depends(bearer),
                     db: oracledb.Connection = Depends(get_db)) -> dict:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in again (session missing or expired)")
    token = bearer_token or request.cookies.get(settings.cookie_name)
    if not token:
        raise unauthorized
    if not bearer_token and request.method not in SAFE_METHODS \
            and request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Request blocked: missing X-Requested-With header (CSRF protection)")
    try:
        user_id = int(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = load_user(db, user_id)
    if user is None or user["account_status"] != "ACTIVE":
        raise unauthorized
    return user


def require(*permissions: str):
    """Route dependency: the logged-in user must have ALL of these permissions."""
    def check(user: dict = Depends(get_current_user)) -> dict:
        missing = [p for p in permissions if p not in user["permissions"]]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"You don't have permission to do this (needs {', '.join(missing)})")
        return user
    return check


def has(user: dict, permission: str) -> bool:
    return permission in user["permissions"]
