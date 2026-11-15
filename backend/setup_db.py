"""Run the SQL scripts in ../database against Oracle, in order.

    python setup_db.py --create-user  # first time only: also creates the INVENTORY user (asks for SYSTEM password)
    python setup_db.py                # tables + package + views + demo data
    python setup_db.py --no-seed      # tables + package + views only

You can also run the same .sql files yourself in SQL Developer (open the file, press F5).
Connection details come from .env / environment variables (see app/config.py).
"""
import getpass
import sys
from pathlib import Path

import oracledb

from app.config import settings

SQL_DIR = Path(__file__).resolve().parent.parent / "database"
PLSQL_START = ("CREATE OR REPLACE PACKAGE", "CREATE OR REPLACE TRIGGER", "CREATE OR REPLACE PROCEDURE",
               "CREATE OR REPLACE FUNCTION", "CREATE OR REPLACE TYPE", "DECLARE", "BEGIN")


def split_statements(sql: str) -> list[str]:
    """Split a script the way SQL Developer does: plain SQL ends with ';',
    PL/SQL blocks end with a line containing only '/'."""
    statements, buf, in_plsql = [], [], False
    for line in sql.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        if not buf:
            in_plsql = stripped.upper().startswith(PLSQL_START)
        if in_plsql:
            if stripped == "/":
                statements.append("\n".join(buf))
                buf = []
            else:
                buf.append(line)
        else:
            code = stripped.split("--")[0].rstrip()   # ignore a trailing comment
            if code.endswith(";"):
                line = line[:line.index(code) + len(code)]
            buf.append(line)
            if code.endswith(";"):
                statements.append("\n".join(buf).rstrip().rstrip(";"))
                buf = []
    if "".join(buf).strip():
        statements.append("\n".join(buf).rstrip().rstrip(";"))
    return statements


def run_file(conn, path: Path):
    print(f"Running {path.name} ...")
    with conn.cursor() as cur:
        for stmt in split_statements(path.read_text(encoding="utf-8")):
            cur.execute(stmt)
            if stmt.lstrip().upper().startswith("SELECT"):
                for row in cur:
                    print("  ", *row)
            if stmt.lstrip().upper().startswith(("CREATE OR REPLACE PACKAGE", "CREATE OR REPLACE TRIGGER")):
                cur.execute("SELECT name, type, line, text FROM user_errors ORDER BY name, type, sequence")
                errors = cur.fetchall()
                if errors:
                    raise SystemExit("PL/SQL compile errors:\n" + "\n".join(map(str, errors)))
    conn.commit()


def create_user():
    """Runs 00_create_user.sql as SYSTEM (the password you chose when installing Oracle)."""
    password = getpass.getpass("Oracle SYSTEM password (the one you chose when installing Oracle): ")
    try:
        conn = oracledb.connect(user="system", password=password, dsn=settings.oracle_dsn)
    except oracledb.Error as exc:
        raise SystemExit(f"Could not log in as SYSTEM at {settings.oracle_dsn}: {str(exc).splitlines()[0]}")
    try:
        run_file(conn, SQL_DIR / "00_create_user.sql")
    finally:
        conn.close()


def main():
    if "--create-user" in sys.argv:
        create_user()
    files = ["01_schema.sql", "02_inventory_pkg.sql"]
    if "--no-seed" not in sys.argv:
        files.append("03_seed_data.sql")
    try:
        conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    except oracledb.Error as exc:
        raise SystemExit(f"Could not connect as {settings.oracle_user} at {settings.oracle_dsn}: "
                         f"{str(exc).splitlines()[0]}\nIs Oracle running? First time? Use: python setup_db.py --create-user")
    try:
        for name in files:
            run_file(conn, SQL_DIR / name)
    finally:
        conn.close()
    print("Done. Admin: admin@inventory.com / admin123   Customer: customer@inventory.com / customer123")


if __name__ == "__main__":
    main()
