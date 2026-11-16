"""Business rules for accounts, logins and access rights."""
from datetime import datetime, timedelta

import oracledb

from ..config import settings
from ..database import call_procedure, query, query_one, transaction
from ..errors import BusinessError, conflict, forbidden, invalid, not_found
from ..schemas import MyProfileIn, ProfileCode, RegisterIn, StaffIn
from ..security import hash_password, verify_password

STAFF_PROFILES = {ProfileCode.ADMIN, ProfileCode.STORE_MANAGER, ProfileCode.WAREHOUSE_STAFF}


def _check_outlet(db: oracledb.Connection, outlet_id: int | None) -> None:
    if outlet_id is not None and not query_one(db, "SELECT 1 AS ok FROM outlets WHERE outlet_id = :id", {"id": outlet_id}):
        raise not_found("Outlet")


def _save_address(db: oracledb.Connection, user_id: int, data) -> None:
    call_procedure(db, "inventory_pkg.save_customer_profile", p_customer_id=user_id, p_phone=data.phone,
                   p_address_line=data.address_line, p_city=data.city, p_state=data.state,
                   p_pincode=data.pincode, p_preferred_outlet_id=data.preferred_outlet_id)


def register_customer(db: oracledb.Connection, data: RegisterIn) -> int:
    """Public sign-up. Always a CUSTOMER: staff accounts are created by an administrator."""
    email = data.email.lower()

    def work():
        if query_one(db, "SELECT 1 AS found FROM users WHERE email = :email", {"email": email}):
            raise conflict("This email is already registered")
        _check_outlet(db, data.preferred_outlet_id)
        user_id = call_procedure(db, "inventory_pkg.create_user", out={"p_user_id": int}, p_full_name=data.name.strip(),
                                 p_email=email, p_password_hash=hash_password(data.password))["p_user_id"]
        call_procedure(db, "inventory_pkg.assign_profile", p_user_id=user_id, p_profile_code=ProfileCode.CUSTOMER.value)
        _save_address(db, user_id, data)
        return user_id
    return transaction(db, work)


def authenticate(db: oracledb.Connection, email: str, password: str) -> int:
    """Checks the password. Too many wrong passwords in a row lock the account for a while."""
    row = query_one(db, """SELECT user_id, password_hash, account_status, failed_login_count, locked_until
                             FROM users WHERE email = :email""", {"email": email.lower()})
    wrong = BusinessError(401, "Incorrect email or password")
    if row is None:
        verify_password(password, "$2b$12$" + "x" * 53)   # same work as a real check, so timing reveals nothing
        raise wrong
    now = datetime.now()
    if row["locked_until"] and row["locked_until"] > now:
        minutes = int((row["locked_until"] - now).total_seconds() // 60) + 1
        raise BusinessError(423, f"Too many wrong passwords. Try again in {minutes} minute(s).")
    if not verify_password(password, row["password_hash"]):
        attempts = row["failed_login_count"] + 1
        lock = now + timedelta(minutes=settings.lock_minutes) if attempts >= settings.max_failed_logins else None
        transaction(db, lambda: call_procedure(db, "inventory_pkg.record_login_failure",
                                               p_user_id=row["user_id"], p_locked_until=lock))
        if lock:
            raise BusinessError(423, f"Too many wrong passwords. The account is locked for {settings.lock_minutes} minutes.")
        raise wrong
    if row["account_status"] != "ACTIVE":
        raise BusinessError(403, "This account has been disabled. Please contact the administrator.")
    transaction(db, lambda: call_procedure(db, "inventory_pkg.record_login_success", p_user_id=row["user_id"]))
    return row["user_id"]


def update_my_profile(db: oracledb.Connection, user: dict, data: MyProfileIn) -> None:
    def work():
        _check_outlet(db, data.preferred_outlet_id)
        call_procedure(db, "inventory_pkg.update_user_name", p_user_id=user["id"], p_full_name=data.name.strip())
        if ProfileCode.CUSTOMER.value in user["profiles"]:
            _save_address(db, user["id"], data)
    transaction(db, work)


def create_staff(db: oracledb.Connection, admin: dict, data: StaffIn) -> int:
    email = data.email.lower()
    profiles = set(data.profiles)
    if not profiles & STAFF_PROFILES:
        raise invalid("A staff account needs at least one staff profile (ADMIN, STORE_MANAGER or WAREHOUSE_STAFF)")

    def work():
        if query_one(db, "SELECT 1 AS found FROM users WHERE email = :email", {"email": email}):
            raise conflict("This email is already registered")
        user_id = call_procedure(db, "inventory_pkg.create_user", out={"p_user_id": int}, p_full_name=data.name.strip(),
                                 p_email=email, p_password_hash=hash_password(data.password))["p_user_id"]
        for code in sorted(p.value for p in profiles):
            call_procedure(db, "inventory_pkg.assign_profile", p_user_id=user_id, p_profile_code=code,
                           p_assigned_by=admin["id"])
        return user_id
    return transaction(db, work)


def set_profiles(db: oracledb.Connection, admin: dict, user_id: int, wanted: list[ProfileCode]) -> None:
    """Replaces a user's profiles. Guards: admins can't remove their own ADMIN profile, and the
    last active administrator can't be removed (someone must always be able to manage access)."""
    wanted_codes = {p.value for p in wanted}

    def work():
        current = {r for r in _profile_codes(db, user_id)}
        if user_id == admin["id"] and "ADMIN" in current and "ADMIN" not in wanted_codes:
            raise forbidden("You can't remove your own ADMIN profile")
        if "ADMIN" in current and "ADMIN" not in wanted_codes and _active_admins(db) <= 1:
            raise conflict("This is the last active administrator")
        for code in sorted(current - wanted_codes):
            call_procedure(db, "inventory_pkg.revoke_profile", p_user_id=user_id, p_profile_code=code)
        for code in sorted(wanted_codes - current):
            call_procedure(db, "inventory_pkg.assign_profile", p_user_id=user_id, p_profile_code=code,
                           p_assigned_by=admin["id"])
        if "CUSTOMER" in wanted_codes and not query_one(
                db, "SELECT 1 AS ok FROM customer_profiles WHERE customer_id = :id", {"id": user_id}):
            call_procedure(db, "inventory_pkg.save_customer_profile", p_customer_id=user_id, p_phone=None,
                           p_address_line=None, p_city=None, p_state=None, p_pincode=None, p_preferred_outlet_id=None)
        call_procedure(db, "inventory_pkg.touch_user", p_user_id=user_id)
    transaction(db, work)


def set_status(db: oracledb.Connection, admin: dict, user_id: int, status: str) -> None:
    def work():
        _lock_user(db, user_id)
        if user_id == admin["id"] and status != "ACTIVE":
            raise forbidden("You can't disable your own account")
        if status != "ACTIVE" and "ADMIN" in _profile_codes(db, user_id) and _active_admins(db) <= 1:
            raise conflict("This is the last active administrator")
        call_procedure(db, "inventory_pkg.set_account_status", p_user_id=user_id, p_status=status)
    transaction(db, work)


def unlock(db: oracledb.Connection, user_id: int) -> None:
    transaction(db, lambda: call_procedure(db, "inventory_pkg.unlock_user", p_user_id=user_id))


def _lock_user(db: oracledb.Connection, user_id: int) -> None:
    if not query_one(db, "SELECT user_id FROM users WHERE user_id = :id FOR UPDATE", {"id": user_id}):
        raise not_found("User")


def _profile_codes(db: oracledb.Connection, user_id: int) -> set[str]:
    if not query_one(db, "SELECT 1 AS ok FROM users WHERE user_id = :id", {"id": user_id}):
        raise not_found("User")
    return {r["profile_code"] for r in query(db, """
        SELECT p.profile_code FROM user_profiles up JOIN profiles p ON p.profile_id = up.profile_id
         WHERE up.user_id = :id""", {"id": user_id})}


def _active_admins(db: oracledb.Connection) -> int:
    return query_one(db, """SELECT COUNT(DISTINCT user_id) AS n FROM v_user_access
                             WHERE profile_code = 'ADMIN' AND account_status = 'ACTIVE'""")["n"]
