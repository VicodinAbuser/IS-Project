"""Data tier connection: a pool of Oracle connections shared by all API requests.

Uses python-oracledb (Oracle's official driver) in "thin" mode, so no Oracle Client
installation is needed.

How Python and Oracle share the work:
  * app/services/*.py   business logic, written in Python. Each action is ONE transaction:
                        run it with `transaction(conn, work)`, which commits at the end or
                        rolls everything back on any error.
  * INVENTORY_PKG       PL/SQL procedures in Oracle that do the actual table changes
                        (called with `call_procedure`). They never commit by themselves.
  * SELECTs             plain SQL through `query` / `query_one`, mostly on views.
"""
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import TypeVar

import oracledb
from fastapi import HTTPException

from .config import settings

_pool: oracledb.ConnectionPool | None = None
T = TypeVar("T")


def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(user=settings.oracle_user, password=settings.oracle_password,
                                     dsn=settings.oracle_dsn, min=1, max=10, increment=1)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close(force=True)
        _pool = None


def get_db() -> Iterator[oracledb.Connection]:
    """FastAPI dependency: borrow a connection for one request, return it afterwards."""
    init_pool()
    conn = _pool.acquire()
    try:
        yield conn
    finally:
        conn.rollback()          # discard anything a failed request left uncommitted
        _pool.release(conn)


# If someone re-runs 02_inventory_pkg.sql while the API is running, Oracle discards the
# package's variables in every open session and the next call fails ONCE with ORA-04068.
# Running the same work again then succeeds.
PACKAGE_RELOADED = {4061, 4065, 4068, 6508}


def _code(exc: oracledb.DatabaseError) -> int | None:
    return getattr(exc.args[0], "code", None)


def _run(conn: oracledb.Connection, work):
    """Run one statement. If it hit a reloaded package and no transaction is open, try once more.
    (Inside a transaction the whole transaction is retried instead, see `transaction`.)"""
    try:
        with conn.cursor() as cur:
            return work(cur)
    except oracledb.DatabaseError as exc:
        if _code(exc) not in PACKAGE_RELOADED or conn.transaction_in_progress:
            raise
        conn.rollback()
        with conn.cursor() as cur:
            return work(cur)


def transaction(conn: oracledb.Connection, work: Callable[[], T]) -> T:
    """Run `work` as ONE database transaction: COMMIT if it finishes, ROLLBACK if anything fails
    (a business rule, an Oracle error, anything). So an action either happens completely or not at all."""
    for attempt in (1, 2):
        try:
            result = work()
            conn.commit()
            return result
        except oracledb.DatabaseError as exc:
            conn.rollback()
            if attempt == 1 and _code(exc) in PACKAGE_RELOADED:
                continue
            raise
        except BaseException:
            conn.rollback()
            raise
    raise RuntimeError("unreachable")


def query(conn: oracledb.Connection, sql: str, params: dict | None = None) -> list[dict]:
    """Run a SELECT and return rows as dictionaries {column_name: value}."""
    def work(cur):
        cur.execute(sql, params or {})
        cols = [d[0].lower() for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return _run(conn, work)


def query_one(conn: oracledb.Connection, sql: str, params: dict | None = None) -> dict | None:
    rows = query(conn, sql, params)
    return rows[0] if rows else None


OUT_TYPES = {int: oracledb.DB_TYPE_NUMBER, float: oracledb.DB_TYPE_NUMBER, str: oracledb.DB_TYPE_VARCHAR,
             datetime: oracledb.DB_TYPE_TIMESTAMP}


def call_procedure(conn: oracledb.Connection, name: str, out: dict[str, type] | None = None, **params) -> dict:
    """Call a stored procedure with named parameters, e.g.
        call_procedure(conn, "inventory_pkg.apply_stock_change", p_product_id=1, p_outlet_id=2, p_change=10, ...)
    `out` lists OUT parameters and their Python type, e.g. out={"p_order_id": int};
    their values come back in a dict. Parameters given in both are IN OUT."""
    out = out or {}

    def work(cur):
        out_vars = {}
        for n, t in out.items():
            out_vars[n] = cur.var(OUT_TYPES[t])
            if n in params:
                out_vars[n].setvalue(0, params[n])
        cur.callproc(name, keyword_parameters={**params, **out_vars})
        result = {}
        for n, v in out_vars.items():
            value = v.getvalue()
            result[n] = int(value) if out[n] is int and value is not None else value
        return result
    return _run(conn, work)


# Oracle error -> HTTP status. These are data-level problems Oracle itself refuses;
# business-rule errors come from app/services as BusinessError instead.
ORA_TO_HTTP = {20004: 404,   # INVENTORY_PKG: the row to change does not exist
               1: 409,       # ORA-00001 unique constraint violated (duplicate SKU / email / phone)
               2291: 422,    # ORA-02291 foreign key: parent row not found
               2292: 409,    # ORA-02292 child rows exist
               2290: 422,    # ORA-02290 check constraint violated
               1400: 422,    # ORA-01400 cannot insert NULL
               12899: 422}   # ORA-12899 value too long for column

FRIENDLY_UNIQUE = {"UQ_USERS_EMAIL": "This email is already registered",
                   "UQ_CUSTPROF_PHONE": "This phone number is already registered",
                   "UQ_PRODUCTS_SKU": "A product with this SKU already exists",
                   "UQ_OUTLETS_NAME": "An outlet with this name already exists"}


def oracle_error_to_http(exc: oracledb.DatabaseError) -> HTTPException | None:
    err = exc.args[0]
    if isinstance(exc, oracledb.OperationalError) or str(getattr(err, "full_code", "")).startswith("DPY-6"):
        return HTTPException(503, "Cannot connect to the Oracle database. Is Oracle running on the laptop?")
    status = ORA_TO_HTTP.get(getattr(err, "code", None))
    if status is None:
        return None
    message = err.message.splitlines()[0]
    if err.code >= 20000:
        message = message.split(": ", 1)[-1]          # drop the "ORA-20004: " prefix
    elif err.code == 1:
        message = next((m for k, m in FRIENDLY_UNIQUE.items() if k in message), "This record already exists")
    elif err.code == 2290 and "CK_INVENTORY_QTY" in message:
        message = "Not enough stock: stock can't go below 0"
    return HTTPException(status, message)
