import oracledb
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from ..database import get_db, insert_returning_id, query_one
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import USER_COLUMNS, create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: oracledb.Connection = Depends(get_db)):
    """Public sign-up. Always creates a CUSTOMER; admins can't self-register."""
    email = data.email.lower()
    if query_one(db, "SELECT 1 AS found FROM app_users WHERE email = :email", {"email": email}):
        raise HTTPException(409, "Email already registered")
    user_id = insert_returning_id(db, """
        INSERT INTO app_users (full_name, email, password_hash, user_role, phone, address)
        VALUES (:name, :email, :hash, 'CUSTOMER', :phone, :address)
        RETURNING user_id INTO :new_id""",
        {"name": data.name, "email": email, "hash": hash_password(data.password),
         "phone": data.phone, "address": data.address})
    db.commit()
    user = query_one(db, f"SELECT {USER_COLUMNS} FROM app_users WHERE user_id = :id", {"id": user_id})
    return TokenOut(access_token=create_access_token(user), user=user)


def _authenticate(db: oracledb.Connection, email: str, password: str) -> dict:
    row = query_one(db, f"SELECT {USER_COLUMNS}, password_hash FROM app_users WHERE email = :email",
                    {"email": email.lower()})
    if not row or not verify_password(password, row.pop("password_hash")):
        raise HTTPException(401, "Incorrect email or password")
    return row


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: oracledb.Connection = Depends(get_db)):
    user = _authenticate(db, data.email, data.password)
    return TokenOut(access_token=create_access_token(user), user=user)


@router.post("/token", include_in_schema=False)
def token(form: OAuth2PasswordRequestForm = Depends(), db: oracledb.Connection = Depends(get_db)):
    """Form-based login used by the 'Authorize' button in Swagger /docs."""
    user = _authenticate(db, form.username, form.password)
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return user
