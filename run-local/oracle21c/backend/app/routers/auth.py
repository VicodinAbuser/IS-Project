"""Sign-up, login / logout (HttpOnly session cookie) and the logged-in user's own profile."""
import oracledb
from fastapi import APIRouter, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm

from ..config import settings
from ..database import get_db
from ..schemas import LoginIn, LoginOut, MyProfileIn, RegisterIn, UserOut
from ..security import clear_session_cookie, create_access_token, get_current_user, load_user, set_session_cookie
from ..services import users

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _login_response(db: oracledb.Connection, response: Response, user_id: int) -> LoginOut:
    set_session_cookie(response, user_id)
    return LoginOut(user=load_user(db, user_id), session_expires_in_minutes=settings.access_token_minutes)


@router.post("/register", response_model=LoginOut, status_code=201)
def register(data: RegisterIn, response: Response, db: oracledb.Connection = Depends(get_db)):
    """Public sign-up. Always creates a CUSTOMER (with a CUSTOMER_PROFILES row) and logs them in."""
    return _login_response(db, response, users.register_customer(db, data))


@router.post("/login", response_model=LoginOut)
def login(data: LoginIn, response: Response, db: oracledb.Connection = Depends(get_db)):
    """Checks the password and sets the session cookie (HttpOnly, Secure, SameSite=Strict)."""
    return _login_response(db, response, users.authenticate(db, data.email, data.password))


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_session_cookie(response)


@router.post("/token", include_in_schema=False)
def token(form: OAuth2PasswordRequestForm = Depends(), db: oracledb.Connection = Depends(get_db)):
    """Used by the 'Authorize' button in Swagger /docs and by scripts: returns a Bearer token."""
    user_id = users.authenticate(db, form.username, form.password)
    return {"access_token": create_access_token(user_id), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    """Who is logged in, with their profiles and permissions (the website shows menus based on these)."""
    return user


@router.put("/me", response_model=UserOut)
def update_me(data: MyProfileIn, db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    """Change your own name and, for customers, phone and delivery address."""
    users.update_my_profile(db, user, data)
    return load_user(db, user["id"])
