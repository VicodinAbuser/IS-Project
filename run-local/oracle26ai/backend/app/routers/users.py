"""Users and access rights (admin pages): who is registered, their profiles and permissions."""
import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db, query, query_one
from ..listing import UPDATED_WITHIN, order_by, updated_within, where_sql
from ..schemas import PermissionOut, ProfileOut, ProfilesIn, StaffIn, StatusIn, UserDetail, UserRow
from ..security import Perm, load_user, require
from ..services import users

router = APIRouter(prefix="/api", tags=["Users & access (admin)"])

USER_SELECT = """
    SELECT u.user_id AS id, u.full_name AS name, u.email, u.account_status, u.created_at, u.updated_at,
           u.last_login_at, u.locked_until, u.failed_login_count,
           cp.phone, cp.address_line, cp.city, cp.state, cp.pincode, ou.name AS preferred_outlet,
           (SELECT LISTAGG(p.profile_code, ',') WITHIN GROUP (ORDER BY p.profile_id)
              FROM user_profiles up JOIN profiles p ON p.profile_id = up.profile_id
             WHERE up.user_id = u.user_id) AS profile_list,
           (SELECT NVL(MAX(p.is_staff), 0) FROM user_profiles up JOIN profiles p ON p.profile_id = up.profile_id
             WHERE up.user_id = u.user_id) AS is_staff,
           (SELECT COUNT(*) FROM orders o WHERE o.customer_id = u.user_id) AS orders,
           (SELECT NVL(SUM(o.total_amount), 0) FROM orders o
             WHERE o.customer_id = u.user_id AND o.order_status = 'PAID') AS total_spent
      FROM users u
      LEFT JOIN customer_profiles cp ON cp.customer_id = u.user_id
      LEFT JOIN outlets ou ON ou.outlet_id = cp.preferred_outlet_id"""

USER_SORTS = {"updated_desc": "u.updated_at DESC", "created_desc": "u.created_at DESC", "created_asc": "u.created_at",
              "name_asc": "u.full_name", "last_login_desc": "u.last_login_at DESC NULLS LAST"}


def _row(r: dict) -> dict:
    return {**r, "profiles": (r.pop("profile_list") or "").split(",") if r.get("profile_list") else [],
            "is_staff": bool(r["is_staff"]), "total_spent": float(r["total_spent"])}


@router.get("/users", response_model=list[UserRow])
def list_users(search: str | None = Query(None, max_length=100), profile: str | None = None,
               status: str | None = Query(None, pattern="^(ACTIVE|DISABLED|LOCKED)$"),
               sort: str | None = None, updated_within_days: int | None = UPDATED_WITHIN,
               limit: int = Query(100, ge=1, le=1000),
               db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.USER_READ))):
    where, params = [], {}
    if search:
        where.append("(UPPER(u.full_name) LIKE UPPER(:q) OR u.email LIKE LOWER(:q) OR cp.phone LIKE :q)")
        params["q"] = f"%{search.strip()}%"
    if profile:
        where.append("""EXISTS (SELECT 1 FROM user_profiles up JOIN profiles p ON p.profile_id = up.profile_id
                                WHERE up.user_id = u.user_id AND p.profile_code = :profile)""")
        params["profile"] = profile
    if status == "LOCKED":
        where.append("u.locked_until > SYSTIMESTAMP")
    elif status:
        where.append("u.account_status = :status")
        params["status"] = status
    updated_within("u.updated_at", updated_within_days, where, params)
    sql = USER_SELECT + where_sql(where) + order_by(sort, USER_SORTS, "updated_desc", "u.user_id DESC")
    return [_row(r) for r in query(db, sql + f" FETCH FIRST {limit} ROWS ONLY", params)]


@router.get("/users/{user_id}", response_model=UserDetail)
def get_user(user_id: int, db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.USER_READ))):
    r = query_one(db, USER_SELECT + " WHERE u.user_id = :id", {"id": user_id})
    if not r:
        raise HTTPException(404, "User not found")
    return {**_row(r), "permissions": load_user(db, user_id)["permissions"]}


@router.post("/users", response_model=UserDetail, status_code=201)
def create_staff(data: StaffIn, db: oracledb.Connection = Depends(get_db),
                 admin: dict = Depends(require(Perm.USER_MANAGE))):
    """Create an employee account (customers sign up themselves)."""
    return get_user(users.create_staff(db, admin, data), db)


@router.put("/users/{user_id}/profiles", response_model=UserDetail)
def set_profiles(user_id: int, data: ProfilesIn, db: oracledb.Connection = Depends(get_db),
                 admin: dict = Depends(require(Perm.USER_MANAGE))):
    users.set_profiles(db, admin, user_id, data.profiles)
    return get_user(user_id, db)


@router.patch("/users/{user_id}/status", response_model=UserDetail)
def set_status(user_id: int, data: StatusIn, db: oracledb.Connection = Depends(get_db),
               admin: dict = Depends(require(Perm.USER_MANAGE))):
    users.set_status(db, admin, user_id, data.status.value)
    return get_user(user_id, db)


@router.post("/users/{user_id}/unlock", response_model=UserDetail)
def unlock(user_id: int, db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.USER_MANAGE))):
    """Clear a lock caused by too many wrong passwords."""
    users.unlock(db, user_id)
    return get_user(user_id, db)


@router.get("/access/profiles", response_model=list[ProfileOut])
def profiles(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.USER_READ))):
    """The authorization matrix: each profile with its permissions and how many users have it."""
    rows = query(db, """
        SELECT p.profile_code AS code, p.profile_name AS name, p.description, p.is_staff,
               (SELECT COUNT(*) FROM user_profiles up WHERE up.profile_id = p.profile_id) AS users,
               (SELECT LISTAGG(pe.permission_code, ',') WITHIN GROUP (ORDER BY pe.permission_id)
                  FROM authorizations a JOIN permissions pe ON pe.permission_id = a.permission_id
                 WHERE a.profile_id = p.profile_id) AS permission_list
          FROM profiles p ORDER BY p.profile_id""")
    return [{**r, "is_staff": bool(r["is_staff"]),
             "permissions": (r.pop("permission_list") or "").split(",") if r.get("permission_list") else []}
            for r in rows]


@router.get("/access/permissions", response_model=list[PermissionOut])
def permissions(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.USER_READ))):
    return query(db, """SELECT permission_code AS code, permission_name AS name, module, access_type, description
                          FROM permissions ORDER BY permission_id""")
