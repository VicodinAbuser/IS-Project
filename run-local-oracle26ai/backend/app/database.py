"""Data tier connection: a pool of Oracle connections shared by all API requests.

Uses python-oracledb (Oracle's official driver) in "thin" mode, so no Oracle Client
installation is needed. Business rules live in the INVENTORY_PKG PL/SQL package;
Python only calls those procedures and runs SELECTs.
"""
from collections.abc import Iterator

import oracledb
from fastapi import HTTPException

from .config import settings

_pool: oracledb.ConnectionPool | None = None


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
# Running the same statement again then works, so we retry once.
PACKAGE_RELOADED = {4061, 4065, 4068, 6508}


def _run(conn: oracledb.Connection, work):
    try:
        with conn.cursor() as cur:
            return work(cur)
    except oracledb.DatabaseError as exc:
        if getattr(exc.args[0], "code", None) not in PACKAGE_RELOADED:
            raise
        conn.rollback()
        with conn.cursor() as cur:
            return work(cur)


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


def execute(conn: oracledb.Connection, sql: str, params: dict | None = None) -> int:
    """Run INSERT/UPDATE/DELETE. Returns rows affected. The caller commits."""
    def work(cur):
        cur.execute(sql, params or {})
        return cur.rowcount
    return _run(conn, work)


def insert_returning_id(conn: oracledb.Connection, sql: str, params: dict) -> int:
    """Run an INSERT ... RETURNING <id> INTO :new_id and give back the new id."""
    def work(cur):
        new_id = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(sql, {**params, "new_id": new_id})
        return int(new_id.getvalue()[0])
    return _run(conn, work)


def call_procedure(conn: oracledb.Connection, name: str, out_numbers: tuple[str, ...] = (), **params) -> dict:
    """Call a stored procedure with named parameters, e.g.
        call_procedure(conn, "inventory_pkg.restock", p_product_id=1, p_outlet_id=2, p_quantity=10)
    Names listed in out_numbers are OUT parameters; their values are returned in a dict."""
    def work(cur):
        outs = {n: cur.var(oracledb.DB_TYPE_NUMBER) for n in out_numbers}
        cur.callproc(name, keyword_parameters={**params, **outs})
        return {n: v.getvalue() for n, v in outs.items()}
    return _run(conn, work)


# Oracle error -> HTTP status. -200xx are our own RAISE_APPLICATION_ERROR codes in INVENTORY_PKG.
ORA_TO_HTTP = {20001: 409, 20004: 404, 20009: 409, 20022: 422,
               1: 409,       # ORA-00001 unique constraint violated (duplicate SKU/email)
               2291: 422,    # ORA-02291 foreign key: parent row not found
               2290: 422,    # ORA-02290 check constraint violated
               1400: 422}    # ORA-01400 cannot insert NULL


def oracle_error_to_http(exc: oracledb.DatabaseError) -> HTTPException | None:
    err = exc.args[0]
    if isinstance(exc, oracledb.OperationalError) or str(getattr(err, "full_code", "")).startswith("DPY-6"):
        return HTTPException(503, "Cannot connect to the Oracle database. Is Oracle running on the laptop?")
    status = ORA_TO_HTTP.get(getattr(err, "code", None))
    if status is None:
        return None
    message = err.message.splitlines()[0]
    if err.code >= 20000:
        message = message.split(": ", 1)[-1]          # drop the "ORA-20001: " prefix
    elif err.code == 1:
        message = "This record already exists (duplicate value)"
    return HTTPException(status, message)
