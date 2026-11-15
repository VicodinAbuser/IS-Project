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
SQLPLUS_ONLY = ("SET ", "PROMPT", "SPOOL", "COLUMN ")
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
        if not buf and stripped.upper().startswith(SQLPLUS_ONLY):
            continue                      # SQL Developer display settings, not SQL
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


def _print_dbms_output(cur) -> None:
    """Show DBMS_OUTPUT.PUT_LINE messages, like SQL Developer's output panel."""
    line, status = cur.var(str), cur.var(int)
    while True:
        cur.callproc("dbms_output.get_line", (line, status))
        if status.getvalue() != 0:
            break
        print("  ", line.getvalue())


def run_file(conn, path: Path):
    print(f"Running {path.name} ...")
    with conn.cursor() as cur:
        cur.callproc("dbms_output.enable")
        for stmt in split_statements(path.read_text(encoding="utf-8")):
            cur.execute(stmt)
            if stmt.lstrip().upper().startswith("SELECT"):
                for row in cur.fetchall():
                    print("  ", *row)
            _print_dbms_output(cur)
            if stmt.lstrip().upper().startswith(("CREATE OR REPLACE PACKAGE", "CREATE OR REPLACE TRIGGER")):
                cur.execute("SELECT name, type, line, text FROM user_errors ORDER BY name, type, sequence")
                errors = cur.fetchall()
                if errors:
                    raise SystemExit("PL/SQL compile errors:\n" + "\n".join(map(str, errors)))
    conn.commit()


ENV_FILE = Path(__file__).resolve().parent / ".env"

# Friendly explanations for the connection errors people hit most often.
HINTS = {
    "ORA-01017": "Wrong password.",
    "ORA-12514": "Oracle doesn't know that service name. 26ai Free uses FREEPDB1; 21c usually ORCLPDB "
                 "(the 'pluggable database name' from the installer). Wait 1-2 minutes after Oracle starts.",
    "ORA-12541": "Oracle isn't running, or uses another port. Start the Oracle services (Win+R -> services.msc).",
    "DPY-6005": "Oracle isn't running, or uses another port. Start the Oracle services (Win+R -> services.msc).",
    "ORA-01109": "The pluggable database is closed (common on 21c after a restart). In SQL Developer connect as "
                 "SYS AS SYSDBA (service ORCLCDB / ORCL) and run: ALTER PLUGGABLE DATABASE ALL OPEN; "
                 "ALTER PLUGGABLE DATABASE ALL SAVE STATE;",
    "ORA-01033": "Oracle is still starting. Wait a minute and try again.",
    "ORA-20000": "Run setup again and type the pluggable database's service name shown above.",
}


def explain(exc: Exception) -> str:
    first = str(exc).splitlines()[0]
    hint = next((h for code, h in HINTS.items() if code in first), "")
    return f"{first}\n  -> {hint}" if hint else first


def save_dsn(dsn: str) -> None:
    """Write ORACLE_DSN into backend/.env (keeping any other settings there) so the API uses it too."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith("ORACLE_DSN=")] + [f"ORACLE_DSN={dsn}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    settings.oracle_dsn = dsn


def choose_dsn() -> None:
    host_port, _, service = settings.oracle_dsn.rpartition("/")
    host, _, port = host_port.rpartition(":")
    print("Which Oracle database? Press Enter to keep the value in [brackets].")
    print("  Service name: FREEPDB1 = Oracle 26ai Free | ORCLPDB = Oracle 21c (usual) | XEPDB1 = Oracle 21c XE")
    service = input(f"  Service name [{service}]: ").strip() or service
    port = input(f"  Port [{port}]: ").strip() or port
    settings.oracle_dsn = f"{host}:{port}/{service}"
    print(f"Using {settings.oracle_dsn}")


def create_user():
    """Runs 00_create_user.sql as SYSTEM (the password you chose when installing Oracle)."""
    choose_dsn()
    password = getpass.getpass("Oracle SYSTEM password (the one you chose when installing Oracle): ")
    try:
        conn = oracledb.connect(user="system", password=password, dsn=settings.oracle_dsn)
    except oracledb.Error as exc:
        raise SystemExit(f"Could not log in as SYSTEM at {settings.oracle_dsn}: {explain(exc)}")
    try:
        run_file(conn, SQL_DIR / "00_create_user.sql")
    except oracledb.DatabaseError as exc:
        raise SystemExit(f"Could not create the project users: {explain(exc)}")
    finally:
        conn.close()
    save_dsn(settings.oracle_dsn)      # it works, so remember it for the API
    print(f"Saved ORACLE_DSN={settings.oracle_dsn} in backend/.env")


def main():
    if "--create-user" in sys.argv:
        create_user()
    files = ["01_schema.sql", "02_inventory_pkg.sql"]
    if "--no-seed" not in sys.argv:
        files.append("03_seed_data.sql")
    try:
        conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    except oracledb.Error as exc:
        raise SystemExit(f"Could not connect as {settings.oracle_user} at {settings.oracle_dsn}: {explain(exc)}\n"
                         "First time on this laptop? Use: python setup_db.py --create-user")
    try:
        for name in files:
            run_file(conn, SQL_DIR / name)
    finally:
        conn.close()
    print("Done. Admin: admin@inventory.com / admin123   Customer: customer@inventory.com / customer123")


if __name__ == "__main__":
    main()
