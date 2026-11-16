"""Load the large dataset (database/dataset/*.csv, 50,000 customers) into Oracle.

    python load_dataset.py          # asks before replacing the data
    python load_dataset.py --yes    # no question

Run it after setup_db.py (the tables and INVENTORY_PKG must exist). It REPLACES all
rows in the project tables with the CSV data. To go back to the small demo data, run
setup_db.py again (or 03_seed_data.sql in SQL Developer).

How it works:
  1. empties the 11 tables (children first, so foreign keys are never broken)
  2. switches the audit trigger TRG_INVENTORY_AUDIT off while loading, because the
     stock history comes from stock_movements.csv (otherwise every INVENTORY row
     inserted would also be logged as a MANUAL movement)
  3. inserts each CSV in batches with bind variables (parents first)
  4. switches the trigger back on, moves every identity column past the loaded IDs
     (so new orders get the next number), recompiles and gathers optimiser statistics
  5. runs checks inside Oracle and prints the row counts
"""
import csv
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import oracledb

from app.config import settings
from setup_db import explain

DATA_DIR = Path(__file__).resolve().parent.parent / "database" / "dataset"
BATCH = 10_000

# table -> (identity column, {column: type}); types: int, money, ts or a VARCHAR2 size
TABLES = {
    "app_users": ("user_id", {"user_id": int, "full_name": 100, "email": 255, "password_hash": 255,
                              "user_role": 10, "phone": 20, "address": 500, "created_at": "ts"}),
    "outlets": ("outlet_id", {"outlet_id": int, "name": 100, "city": 100, "address": 500}),
    "categories": ("category_id", {"category_id": int, "name": 100}),
    "suppliers": ("supplier_id", {"supplier_id": int, "name": 150, "contact_email": 255, "phone": 20}),
    "products": ("product_id", {"product_id": int, "sku": 50, "name": 150, "description": 1000, "price": "money",
                                "image_url": 500, "reorder_level": int, "is_active": int, "category_id": int,
                                "supplier_id": int, "created_at": "ts"}),
    "inventory": ("inventory_id", {"inventory_id": int, "product_id": int, "outlet_id": int, "quantity": int,
                                   "updated_at": "ts"}),
    "orders": ("order_id", {"order_id": int, "customer_id": int, "outlet_id": int, "order_status": 20,
                            "total_amount": "money", "shipping_address": 500, "created_at": "ts"}),
    "order_items": ("order_item_id", {"order_item_id": int, "order_id": int, "product_id": int, "quantity": int,
                                      "unit_price": "money"}),
    "payments": ("payment_id", {"payment_id": int, "order_id": int, "amount": "money", "payment_method": 30,
                                "payment_status": 20, "transaction_ref": 100, "updated_at": "ts"}),
    "deliveries": ("delivery_id", {"delivery_id": int, "order_id": int, "delivery_status": 20, "courier": 100,
                                   "tracking_number": 100, "updated_at": "ts"}),
    "stock_movements": ("movement_id", {"movement_id": int, "product_id": int, "outlet_id": int, "qty_change": int,
                                        "movement_type": 20, "note": 255, "order_id": int, "user_id": int,
                                        "created_at": "ts"}),
}

CONVERT = {int: int, "money": Decimal, "ts": lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")}
BIND_TYPE = {int: oracledb.DB_TYPE_NUMBER, "money": oracledb.DB_TYPE_NUMBER, "ts": oracledb.DB_TYPE_TIMESTAMP}

CHECKS = [  # (what, SQL returning the number of bad rows)
    ("inventory = sum of stock movements",
     """SELECT COUNT(*) FROM inventory i
         WHERE i.quantity <> (SELECT NVL(SUM(m.qty_change), 0) FROM stock_movements m
                               WHERE m.product_id = i.product_id AND m.outlet_id = i.outlet_id)"""),
    ("order total = sum of its items",
     """SELECT COUNT(*) FROM orders o
         WHERE o.total_amount <> (SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi WHERE oi.order_id = o.order_id)"""),
    ("payment amount = order total",
     "SELECT COUNT(*) FROM orders o JOIN payments p ON p.order_id = o.order_id WHERE p.amount <> o.total_amount"),
    ("every order has a payment and a delivery",
     """SELECT COUNT(*) FROM orders o
         WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)
            OR NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.order_id = o.order_id)"""),
    ("invalid database objects",
     "SELECT COUNT(*) FROM user_objects WHERE status <> 'VALID'"),
]


def read_csv(table, types):
    with open(DATA_DIR / f"{table}.csv", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = [h.lower() for h in next(reader)]
        if header != list(types):
            raise SystemExit(f"{table}.csv: columns {header} don't match the table {list(types)}")
        conv = [CONVERT.get(t, str) for t in types.values()]
        for row in reader:
            yield [None if v == "" else c(v) for c, v in zip(conv, row)]


def load_table(cur, table, types):
    cols = list(types)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + str(i + 1) for i in range(len(cols)))})"
    cur.setinputsizes(*[BIND_TYPE.get(t, t) for t in types.values()])
    batch, total = [], 0
    for row in read_csv(table, types):
        batch.append(row)
        if len(batch) == BATCH:
            cur.executemany(sql, batch)
            total += len(batch)
            batch = []
            print(f"\r  {table:<16} {total:>8,} rows", end="", flush=True)
    if batch:
        cur.executemany(sql, batch)
        total += len(batch)
    print(f"\r  {table:<16} {total:>8,} rows")
    return total


def main():
    if not (DATA_DIR / "app_users.csv").exists():
        raise SystemExit(f"No dataset found in {DATA_DIR}")
    print(f"This REPLACES all data in the INVENTORY tables at {settings.oracle_dsn}")
    print("with the large dataset (50,000 customers, about 89,000 orders).")
    if "--yes" not in sys.argv and input("Continue? Type Y and press Enter: ").strip().lower() not in ("y", "yes"):
        raise SystemExit("Nothing changed.")
    try:
        conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    except oracledb.Error as exc:
        raise SystemExit(f"Could not connect as {settings.oracle_user} at {settings.oracle_dsn}: {explain(exc)}")

    started = time.time()
    cur = conn.cursor()
    names = [t.upper() for t in TABLES]
    cur.execute(f"SELECT COUNT(*) FROM user_tables WHERE table_name IN ({', '.join(':' + str(i + 1) for i in range(len(names)))})", names)
    if cur.fetchone()[0] != len(names):
        raise SystemExit("The project tables don't exist yet. Run setup_db.py (2-setup-database.bat) first.")

    try:
        print("Emptying the tables ...")
        for table in reversed(TABLES):          # children first
            cur.execute(f"DELETE FROM {table}")
        conn.commit()
        cur.execute("ALTER TRIGGER trg_inventory_audit DISABLE")
        print(f"Loading CSV files from {DATA_DIR}")
        for table, (_, types) in TABLES.items():   # parents first
            load_table(conn.cursor(), table, types)
            conn.commit()
    except oracledb.DatabaseError as exc:
        conn.rollback()
        raise SystemExit(f"Loading failed: {explain(exc)}\nFix the problem and run this again (it starts from empty tables).")
    finally:
        cur.execute("ALTER TRIGGER trg_inventory_audit ENABLE")

    print("Moving the ID counters past the loaded rows, recompiling, gathering statistics ...")
    for table, (id_col, _) in TABLES.items():
        cur.execute(f"ALTER TABLE {table} MODIFY {id_col} GENERATED BY DEFAULT AS IDENTITY (START WITH LIMIT VALUE)")
    cur.execute("BEGIN DBMS_UTILITY.COMPILE_SCHEMA(schema => USER, compile_all => FALSE); END;")
    cur.execute("BEGIN DBMS_STATS.GATHER_SCHEMA_STATS(ownname => USER); END;")

    print("Checking the data inside Oracle ...")
    failed = 0
    for what, sql in CHECKS:
        cur.execute(sql)
        n = cur.fetchone()[0]
        failed += n
        print(f"  {'OK ' if n == 0 else 'BAD'}  {what}" + (f"  ({n} rows)" if n else ""))
    cur.execute("""SELECT (SELECT COUNT(*) FROM app_users WHERE user_role = 'CUSTOMER'),
                          (SELECT COUNT(*) FROM orders), (SELECT COUNT(*) FROM order_items),
                          (SELECT COUNT(*) FROM stock_movements) FROM dual""")
    c, o, i, m = cur.fetchone()
    conn.close()
    print(f"Loaded {c:,} customers, {o:,} orders, {i:,} order items, {m:,} stock movements "
          f"in {time.time() - started:.0f} s.")
    print("Logins: admin@inventory.com / admin123, and every customer (e.g. customer@inventory.com) uses customer123.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
