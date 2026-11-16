"""Check database/dataset/*.csv against the schema (01_schema.sql) and the rules of INVENTORY_PKG.

    python tools/validate_dataset.py [folder]

It reads only the CSV files (not the generator), so it is an independent check.
Prints every problem found and exits with code 1 if there are any.
"""
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

FOLDER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "database" / "dataset"
problems = []


def bad(msg):
    problems.append(msg)
    if len(problems) <= 50:
        print("  PROBLEM:", msg)


def load(table):
    with open(FOLDER / f"{table}.csv", newline="", encoding="utf-8") as f:
        rows = [{k.lower(): v for k, v in r.items()} for r in csv.DictReader(f)]
    print(f"  read {table}.csv: {len(rows):,} rows")
    return rows


def ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def check_pk(rows, col, table):
    ids = [int(r[col]) for r in rows]
    if len(set(ids)) != len(ids):
        bad(f"{table}: duplicate {col}")
    return {int(r[col]): r for r in rows}


def check_unique(rows, cols, table, allow_null=False):
    seen = Counter(tuple(r[c] for c in cols) for r in rows if not (allow_null and all(r[c] == "" for c in cols)))
    dups = [k for k, n in seen.items() if n > 1]
    if dups:
        bad(f"{table}: {len(dups)} duplicate values in UNIQUE {cols}, e.g. {dups[0]}")


def check_len(rows, limits, table):
    for c, n in limits.items():
        longest = max((len(r[c]) for r in rows), default=0)
        if longest > n:
            bad(f"{table}.{c}: value of length {longest} > VARCHAR2({n})")


def check_not_null(rows, cols, table):
    for c in cols:
        if any(r[c] == "" for r in rows):
            bad(f"{table}.{c}: empty value in a NOT NULL column")


def check_fk(rows, col, parent, table, nullable=False):
    for r in rows:
        if r[col] == "" and nullable:
            continue
        if r[col] == "" or int(r[col]) not in parent:
            bad(f"{table}.{col}={r[col]!r} has no parent row")
            return


print(f"Checking {FOLDER}")
users = load("users"); outlets = load("outlets"); categories = load("categories"); suppliers = load("suppliers")
cprofiles = load("customer_profiles"); profiles = load("profiles"); permissions = load("permissions")
authz = load("authorizations"); uprofiles = load("user_profiles")
products = load("products"); inventory = load("inventory"); orders = load("orders"); items = load("order_items")
payments = load("payments"); deliveries = load("deliveries"); moves = load("stock_movements")

# ---------------------------------------------------------------- schema constraints
U = check_pk(users, "user_id", "users")
check_not_null(users, ["full_name", "email", "password_hash", "account_status", "failed_login_count", "created_at",
                       "updated_at"], "users")
check_unique(users, ["email"], "users")
check_len(users, {"full_name": 100, "email": 255, "password_hash": 255, "account_status": 10}, "users")
if any(r["email"] != r["email"].lower() for r in users):
    bad("users.email must be lower case (CHECK ck_users_email_lower)")
if {r["account_status"] for r in users} - {"ACTIVE", "DISABLED"}:
    bad("users.account_status outside ('ACTIVE','DISABLED')")
if any(int(r["failed_login_count"]) < 0 for r in users):
    bad("users.failed_login_count < 0")
if any(not r["password_hash"].startswith("$2b$") for r in users):
    bad("users.password_hash is not a bcrypt hash")

# access control: profiles, permissions, the authorization matrix and each user's profiles
PR = check_pk(profiles, "profile_id", "profiles"); check_unique(profiles, ["profile_code"], "profiles")
PE = check_pk(permissions, "permission_id", "permissions"); check_unique(permissions, ["permission_code"], "permissions")
if {r["module"] for r in permissions} - {"CATALOG", "ORDERS", "INVENTORY", "REPORTS", "USERS"}:
    bad("permissions.module outside the allowed values")
if {r["access_type"] for r in permissions} - {"READ", "WRITE", "REPORT", "DOWNLOAD", "ADMIN"}:
    bad("permissions.access_type outside the allowed values")
check_unique(authz, ["profile_id", "permission_id"], "authorizations")
check_fk(authz, "profile_id", PR, "authorizations"); check_fk(authz, "permission_id", PE, "authorizations")
check_fk(authz, "granted_by", U, "authorizations", nullable=True)
check_unique(uprofiles, ["user_id", "profile_id"], "user_profiles")
check_fk(uprofiles, "user_id", U, "user_profiles"); check_fk(uprofiles, "profile_id", PR, "user_profiles")
check_fk(uprofiles, "assigned_by", U, "user_profiles", nullable=True)
code_of = {int(r["profile_id"]): r["profile_code"] for r in profiles}
perm_code = {int(r["permission_id"]): r["permission_code"] for r in permissions}
grants = defaultdict(set)
for a in authz:
    grants[code_of[int(a["profile_id"])]].add(perm_code[int(a["permission_id"])])
user_codes = defaultdict(set)
for up in uprofiles:
    user_codes[int(up["user_id"])].add(code_of[int(up["profile_id"])])
user_perms = {uid: set().union(*(grants[c] for c in codes)) for uid, codes in user_codes.items()}
if set(U) - set(user_codes):
    bad(f"{len(set(U) - set(user_codes))} users have no profile")
customers = {uid for uid, codes in user_codes.items() if "CUSTOMER" in codes}
if len(customers) != 50_000:
    bad(f"expected 50,000 customers, found {len(customers):,}")
if grants["CUSTOMER"] != {"CATALOG_READ", "ORDER_PLACE", "ORDER_READ_OWN"} or len(grants["ADMIN"]) != len(permissions):
    bad("the authorization matrix differs from 01_schema.sql")

CP = check_pk(cprofiles, "customer_id", "customer_profiles")
check_fk(cprofiles, "customer_id", U, "customer_profiles")
check_unique(cprofiles, ["phone"], "customer_profiles", allow_null=True)
check_len(cprofiles, {"phone": 20, "address_line": 300, "city": 100, "state": 100, "pincode": 10}, "customer_profiles")
if any(r["pincode"] and not (len(r["pincode"]) == 6 and r["pincode"].isdigit()) for r in cprofiles):
    bad("customer_profiles.pincode is not 6 digits (CHECK ck_custprof_pincode)")
if set(CP) != customers:
    bad("customer_profiles must have exactly one row per CUSTOMER user")

O = check_pk(outlets, "outlet_id", "outlets")
check_not_null(outlets, ["name", "city"], "outlets"); check_unique(outlets, ["name"], "outlets")
check_len(outlets, {"name": 100, "city": 100, "address": 500}, "outlets")
C = check_pk(categories, "category_id", "categories"); check_unique(categories, ["name"], "categories")
S = check_pk(suppliers, "supplier_id", "suppliers"); check_unique(suppliers, ["name"], "suppliers")
check_len(suppliers, {"name": 150, "contact_email": 255, "phone": 20}, "suppliers")

P = check_pk(products, "product_id", "products")
check_not_null(products, ["sku", "name", "price", "reorder_level", "is_active", "created_at", "updated_at"], "products")
check_unique(products, ["sku"], "products")
check_len(products, {"sku": 50, "name": 150, "description": 1000, "image_url": 500}, "products")
check_fk(products, "category_id", C, "products", nullable=True)
check_fk(products, "supplier_id", S, "products", nullable=True)
check_fk(cprofiles, "preferred_outlet_id", O, "customer_profiles", nullable=True)
for p in products:
    if Decimal(p["price"]) < 0 or int(p["reorder_level"]) < 0 or p["is_active"] not in ("0", "1"):
        bad(f"products {p['sku']}: CHECK constraint fails")

I = check_pk(inventory, "inventory_id", "inventory")
check_unique(inventory, ["product_id", "outlet_id"], "inventory")
check_fk(inventory, "product_id", P, "inventory"); check_fk(inventory, "outlet_id", O, "inventory")
if any(int(r["quantity"]) < 0 for r in inventory):
    bad("inventory.quantity < 0")

OR = check_pk(orders, "order_id", "orders")
check_not_null(orders, ["customer_id", "outlet_id", "order_status", "total_amount", "shipping_address", "created_at",
                        "updated_at"], "orders")
check_fk(orders, "customer_id", U, "orders"); check_fk(orders, "outlet_id", O, "orders")
check_len(orders, {"shipping_address": 500}, "orders")
if {r["order_status"] for r in orders} - {"PENDING_PAYMENT", "PAID", "CANCELLED", "RETURNED"}:
    bad("orders.order_status outside the allowed values")
if any(int(r["customer_id"]) not in customers for r in orders):
    bad("an order belongs to a user without the CUSTOMER profile")

check_pk(items, "order_item_id", "order_items")
check_fk(items, "order_id", OR, "order_items"); check_fk(items, "product_id", P, "order_items")
if any(int(r["quantity"]) <= 0 for r in items):
    bad("order_items.quantity <= 0")
check_unique(items, ["order_id", "product_id"], "order_items")   # place_order merges duplicates

PAY = check_pk(payments, "payment_id", "payments")
check_unique(payments, ["order_id"], "payments"); check_unique(payments, ["transaction_ref"], "payments", allow_null=True)
check_fk(payments, "order_id", OR, "payments")
if {r["payment_method"] for r in payments} - {"", "CARD", "UPI", "NETBANKING"}:
    bad("payments.payment_method outside the allowed values")
if {r["payment_status"] for r in payments} - {"PENDING", "SUCCESS", "FAILED", "REFUNDED", "CANCELLED"}:
    bad("payments.payment_status outside the allowed values")

check_pk(deliveries, "delivery_id", "deliveries")
check_unique(deliveries, ["order_id"], "deliveries"); check_fk(deliveries, "order_id", OR, "deliveries")
if {r["delivery_status"] for r in deliveries} - {"NOT_SHIPPED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED"}:
    bad("deliveries.delivery_status outside the allowed values")

M = check_pk(moves, "movement_id", "stock_movements")
check_fk(moves, "product_id", P, "stock_movements"); check_fk(moves, "outlet_id", O, "stock_movements")
check_fk(moves, "order_id", OR, "stock_movements", nullable=True); check_fk(moves, "user_id", U, "stock_movements", nullable=True)
check_len(moves, {"note": 255}, "stock_movements")
if {r["movement_type"] for r in moves} - {"RESTOCK", "SALE", "CANCEL", "RETURN", "ADJUSTMENT", "TRANSFER_IN", "TRANSFER_OUT", "MANUAL"}:
    bad("stock_movements.movement_type outside the allowed values")
if any(int(r["qty_change"]) == 0 for r in moves):
    bad("stock_movements.qty_change = 0 (the trigger never logs a zero change)")

# every timestamp parses
for table, rows, col in [("users", users, "created_at"), ("users", users, "updated_at"),
                         ("customer_profiles", cprofiles, "created_at"), ("customer_profiles", cprofiles, "updated_at"),
                         ("user_profiles", uprofiles, "assigned_at"), ("authorizations", authz, "granted_at"),
                         ("products", products, "created_at"), ("products", products, "updated_at"),
                         ("orders", orders, "updated_at"),
                         ("inventory", inventory, "updated_at"), ("orders", orders, "created_at"),
                         ("payments", payments, "updated_at"), ("deliveries", deliveries, "updated_at"),
                         ("stock_movements", moves, "created_at")]:
    for r in rows:
        r[col] = ts(r[col])

for table, rows, col in [("users", users, "last_login_at")]:
    for r in rows:
        r[col] = ts(r[col]) if r[col] else None

# ---------------------------------------------------------------- business rules
print("  checking business rules ...")
for u in users:
    if u["updated_at"] < u["created_at"] or (u["last_login_at"] and u["last_login_at"] < u["created_at"]):
        bad(f"user {u['user_id']}: updated / last login before the account was created"); break
for r in cprofiles:
    if r["created_at"] < U[int(r["customer_id"])]["created_at"] or r["updated_at"] < r["created_at"]:
        bad(f"customer_profiles {r['customer_id']}: dates out of order"); break
for p in products:
    if p["updated_at"] < p["created_at"]:
        bad(f"product {p['sku']}: updated before it was created")
items_by_order = defaultdict(list)
for it in items:
    items_by_order[int(it["order_id"])].append(it)
pay_by_order = {int(p["order_id"]): p for p in payments}
del_by_order = {int(d["order_id"]): d for d in deliveries}
moves_by_order = defaultdict(list)
for m in moves:
    if m["order_id"]:
        moves_by_order[int(m["order_id"])].append(m)

ALLOWED = {  # (order_status, payment_status) -> delivery statuses the package can produce
    ("PAID", "SUCCESS"): {"PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"},
    ("CANCELLED", "CANCELLED"): {"NOT_SHIPPED"},
    ("CANCELLED", "REFUNDED"): {"PACKED", "NOT_SHIPPED"},
    ("RETURNED", "REFUNDED"): {"RETURNED"},
    ("PENDING_PAYMENT", "PENDING"): {"NOT_SHIPPED"},
    ("PENDING_PAYMENT", "FAILED"): {"NOT_SHIPPED"},
}
prev_created = None
for o in orders:
    oid = int(o["order_id"])
    lines = items_by_order.get(oid)
    if not lines:
        bad(f"order {oid} has no items"); continue
    total = sum(Decimal(i["unit_price"]) * int(i["quantity"]) for i in lines)
    if total != Decimal(o["total_amount"]):
        bad(f"order {oid}: total_amount {o['total_amount']} != sum of items {total}")
    for i in lines:
        if Decimal(i["unit_price"]) != Decimal(P[int(i["product_id"])]["price"]):
            bad(f"order {oid}: unit_price differs from the product price")
    pay, dl = pay_by_order.get(oid), del_by_order.get(oid)
    if not pay or not dl:
        bad(f"order {oid}: missing payment or delivery row"); continue
    if Decimal(pay["amount"]) != total:
        bad(f"order {oid}: payment amount != order total")
    combo = (o["order_status"], pay["payment_status"])
    if combo not in ALLOWED or dl["delivery_status"] not in ALLOWED[combo]:
        bad(f"order {oid}: impossible status combination {combo} + {dl['delivery_status']}")
    if pay["payment_status"] in ("SUCCESS", "REFUNDED") and (not pay["transaction_ref"] or not pay["payment_method"]):
        bad(f"order {oid}: a paid order needs a payment method and transaction_ref")
    if pay["payment_status"] in ("CANCELLED", "PENDING", "FAILED") and pay["transaction_ref"]:
        bad(f"order {oid}: an unpaid order has a transaction_ref")
    shipped = dl["delivery_status"] in ("SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED")
    if shipped != bool(dl["courier"] and dl["tracking_number"]):
        bad(f"order {oid}: courier/tracking should be set exactly when the order has shipped")
    # dates in order
    if o["created_at"] < U[int(o["customer_id"])]["created_at"]:
        bad(f"order {oid}: placed before the customer signed up")
    if pay["updated_at"] < o["created_at"] or dl["updated_at"] < o["created_at"]:
        bad(f"order {oid}: payment/delivery updated before the order was placed")
    if o["updated_at"] < max(o["created_at"], pay["updated_at"], dl["updated_at"]):
        bad(f"order {oid}: updated_at is older than its payment/delivery change (triggers keep it the latest)")
    if not datetime(2025, 1, 1) <= o["created_at"] <= datetime(2026, 11, 15, 20):
        bad(f"order {oid}: outside the trading period 2025-01-01 .. 2026-11-15 20:00")
    if prev_created and o["created_at"] < prev_created:
        bad(f"order {oid}: order_id is not in time order")
    prev_created = o["created_at"]
    for i in lines:
        if o["created_at"] < P[int(i["product_id"])]["created_at"]:
            bad(f"order {oid}: product sold before it was added to the catalogue")

    # stock movements of the order match its items exactly
    ms = moves_by_order.get(oid, [])
    want = Counter((int(i["product_id"]), -int(i["quantity"])) for i in lines)
    got_sale = Counter((int(m["product_id"]), int(m["qty_change"])) for m in ms if m["movement_type"] == "SALE")
    if got_sale != want:
        bad(f"order {oid}: SALE movements don't match the items")
    back = Counter((int(m["product_id"]), int(m["qty_change"])) for m in ms if m["movement_type"] in ("CANCEL", "RETURN"))
    if o["order_status"] in ("CANCELLED", "RETURNED"):
        if back != Counter({(p, -q): n for (p, q), n in want.items()}):
            bad(f"order {oid}: cancelled/returned but its items weren't put back exactly")
        kind = {m["movement_type"] for m in ms if m["movement_type"] in ("CANCEL", "RETURN")}
        if kind != ({"RETURN"} if o["order_status"] == "RETURNED" else {"CANCEL"}):
            bad(f"order {oid}: wrong movement type for a {o['order_status']} order")
    elif back:
        bad(f"order {oid}: {o['order_status']} order has CANCEL/RETURN movements")
    for m in ms:
        if int(m["outlet_id"]) != int(o["outlet_id"]):
            bad(f"order {oid}: stock moved at a different outlet than the order's")
        if m["movement_type"] == "SALE" and (m["created_at"] != o["created_at"] or int(m["user_id"]) != int(o["customer_id"])):
            bad(f"order {oid}: SALE movement time/user differs from the order")

for m in moves:
    if m["movement_type"] in ("SALE", "CANCEL", "RETURN") and not m["order_id"]:
        bad(f"movement {m['movement_id']}: {m['movement_type']} without an order_id")
    if m["movement_type"] in ("RESTOCK", "ADJUSTMENT", "TRANSFER_IN", "TRANSFER_OUT"):
        if m["order_id"] or not m["user_id"] or "STOCK_WRITE" not in user_perms.get(int(m["user_id"]), set()):
            bad(f"movement {m['movement_id']}: stock changes by staff need a user with STOCK_WRITE and no order"); break
    if m["movement_type"] == "RETURN" and m["user_id"] and "ORDER_MANAGE" not in user_perms.get(int(m["user_id"]), set()):
        bad(f"movement {m['movement_id']}: a return must be accepted by staff with ORDER_MANAGE"); break
    sign_ok = {"RESTOCK": 1, "SALE": -1, "CANCEL": 1, "RETURN": 1, "TRANSFER_IN": 1, "TRANSFER_OUT": -1}
    if m["movement_type"] in sign_ok and int(m["qty_change"]) * sign_ok[m["movement_type"]] < 0:
        bad(f"movement {m['movement_id']}: {m['movement_type']} with the wrong sign")

# transfers come in OUT/IN pairs of the same quantity and time
tin = Counter((m["product_id"], m["qty_change"], m["created_at"]) for m in moves if m["movement_type"] == "TRANSFER_IN")
tout = Counter((m["product_id"], str(-int(m["qty_change"])), m["created_at"]) for m in moves if m["movement_type"] == "TRANSFER_OUT")
if tin != tout:
    bad("TRANSFER_IN and TRANSFER_OUT movements don't pair up")

# replaying the movements in time order: stock never below 0 and ends at INVENTORY.QUANTITY
running = defaultdict(int)
last = {}
prev = None
for m in sorted(moves, key=lambda m: (m["created_at"], int(m["movement_id"]))):
    key = (int(m["product_id"]), int(m["outlet_id"]))
    running[key] += int(m["qty_change"])
    last[key] = m["created_at"]
    if running[key] < 0:
        bad(f"stock of product {key[0]} at outlet {key[1]} goes below 0 at movement {m['movement_id']}"); break
    if m["created_at"] < P[key[0]]["created_at"]:
        bad(f"movement {m['movement_id']} is before its product was created"); break
ids_in_time = [int(m["movement_id"]) for m in sorted(moves, key=lambda m: (m["created_at"], int(m["movement_id"])))]
if ids_in_time != sorted(ids_in_time):
    bad("stock_movements.movement_id is not in time order")
inv_keys = set()
for r in inventory:
    key = (int(r["product_id"]), int(r["outlet_id"]))
    inv_keys.add(key)
    if running[key] != int(r["quantity"]):
        bad(f"inventory {key}: quantity {r['quantity']} != sum of movements {running[key]}")
    if last.get(key) != r["updated_at"]:
        bad(f"inventory {key}: updated_at is not the time of its last movement")
if set(running) - inv_keys:
    bad("movements exist for a product/outlet with no inventory row")

latest = max(max(m["created_at"] for m in moves), max(p["updated_at"] for p in payments), max(d["updated_at"] for d in deliveries))
print(f"  latest timestamp in the data: {latest}")

st = Counter(o["order_status"] for o in orders)
print("  order status:   " + ", ".join(f"{k} {v:,}" for k, v in st.most_common()))
print("  delivery status:" + ", ".join(f" {k} {v:,}" for k, v in Counter(d["delivery_status"] for d in deliveries).most_common()))
print("  low-stock rows: " + str(sum(int(r["quantity"]) <= int(P[int(r["product_id"])]["reorder_level"]) for r in inventory)))
if problems:
    print(f"FAILED: {len(problems)} problem(s)")
    sys.exit(1)
print("OK: every check passed")
