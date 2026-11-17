"""API tests against a real Oracle database.

They use a SEPARATE schema (default INVENTORY_TEST, created by database/00_create_user.sql)
and rebuild it before each test, so your demo data in INVENTORY is never touched.
Run: pytest -q
"""
import os

os.environ["ORACLE_USER"] = os.getenv("TEST_ORACLE_USER", "inventory_test")
os.environ["ORACLE_PASSWORD"] = os.getenv("TEST_ORACLE_PASSWORD", "inventory123")

import threading

import oracledb
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.errors import BusinessError
from app.main import app
from app.schemas import OrderIn
from app.security import hash_password
from app.services import orders as order_service
from setup_db import SQL_DIR, run_file

CSRF = {"X-Requested-With": "XMLHttpRequest"}


def connect():
    return oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)


def make_user(name, email, password, *profiles):
    conn = connect()
    with conn.cursor() as cur:
        uid = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.callproc("inventory_pkg.create_user", [name, email, hash_password(password), uid])
        for p in profiles:
            cur.callproc("inventory_pkg.assign_profile", [uid.getvalue(), p])
    conn.commit()
    conn.close()


@pytest.fixture()
def client():
    conn = connect()
    for name in ("01_schema.sql", "02_inventory_pkg.sql"):
        run_file(conn, SQL_DIR / name)
    conn.close()
    make_user("Admin", "admin@test.com", "admin123", "ADMIN")
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def auth(client, email, password):
    """Bearer token (as Swagger / scripts use it), so one client can act as several users."""
    r = client.post("/api/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register(client, email="c@test.com", **extra):
    body = {"name": "Cust", "email": email, "password": "secret12", **extra}
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201, r.text
    client.cookies.clear()
    return auth(client, email, "secret12")


def setup_catalog(client, admin):
    outlet = client.post("/api/outlets", json={"name": "Test Outlet", "city": "Mumbai"}, headers=admin).json()
    product = client.post("/api/products", json={"sku": "T-1", "name": "Test Item", "price": 100,
                                                  "reorder_level": 3}, headers=admin).json()
    r = client.post("/api/inventory/restock", json={"product_id": product["id"], "outlet_id": outlet["id"],
                                                    "quantity": 10}, headers=admin)
    assert r.status_code == 200 and r.json()["quantity"] == 10
    return outlet, product


def _order(client, headers, outlet, product, qty):
    return client.post("/api/orders", json={"outlet_id": outlet["id"], "shipping_address": "1 Test Street",
                                            "items": [{"product_id": product["id"], "quantity": qty}]}, headers=headers)


# ------------------------------------------------------------------ login, cookie, CSRF, headers
def test_login_sets_httponly_secure_cookie_and_csrf_is_enforced(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "admin123"})
    assert r.status_code == 200 and "access_token" not in r.json()          # the token is NOT readable by the page
    cookie = r.headers["set-cookie"].lower()
    for flag in ("httponly", "secure", "samesite=strict", "path=/api"):
        assert flag in cookie
    assert client.get("/api/auth/me").json()["email"] == "admin@test.com"   # the cookie logs us in
    body = {"name": "Xo", "city": "Pune"}
    assert client.post("/api/outlets", json=body).status_code == 403          # no CSRF header -> blocked
    assert client.post("/api/outlets", json=body, headers=CSRF).status_code == 201
    assert client.post("/api/auth/logout", headers=CSRF).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-xss-protection"] == "0"
    assert r.headers["cache-control"] == "no-store"
    assert "max-age" in r.headers["strict-transport-security"]


def test_wrong_passwords_lock_the_account(client):
    for _ in range(settings.max_failed_logins - 1):
        assert client.post("/api/auth/login", json={"email": "admin@test.com", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "admin@test.com", "password": "nope"}).status_code == 423
    # even the right password is refused while locked
    assert client.post("/api/auth/login", json={"email": "admin@test.com", "password": "admin123"}).status_code == 423
    conn = connect()
    with conn.cursor() as cur:
        cur.callproc("inventory_pkg.unlock_user", [1])
    conn.commit()
    conn.close()
    assert client.post("/api/auth/login", json={"email": "admin@test.com", "password": "admin123"}).status_code == 200


# ------------------------------------------------------------------ profiles and permissions
def test_permissions_per_profile(client):
    assert client.get("/api/products").status_code == 401
    admin = auth(client, "admin@test.com", "admin123")
    make_user("Manager", "m@test.com", "manager123", "STORE_MANAGER")
    make_user("Ware", "w@test.com", "ware12345", "WAREHOUSE_STAFF")
    manager, ware = auth(client, "m@test.com", "manager123"), auth(client, "w@test.com", "ware12345")
    cust = register(client)
    outlet, product = setup_catalog(client, admin)
    restock = {"product_id": product["id"], "outlet_id": outlet["id"], "quantity": 1}

    assert client.post("/api/inventory/restock", json=restock, headers=manager).status_code == 200
    assert client.post("/api/inventory/restock", json=restock, headers=ware).status_code == 200
    assert client.post("/api/inventory/restock", json=restock, headers=cust).status_code == 403
    assert client.get("/api/reports/dashboard", headers=manager).status_code == 200
    assert client.get("/api/reports/dashboard", headers=ware).status_code == 403            # no REPORT_VIEW
    assert client.get("/api/users", headers=manager).status_code == 200                     # USER_READ
    assert client.post("/api/users", json={"name": "New", "email": "n@test.com", "password": "password1",
                                           "profiles": ["WAREHOUSE_STAFF"]}, headers=manager).status_code == 403
    assert client.post("/api/products", json={"sku": "X", "name": "Nope", "price": 1}, headers=cust).status_code == 403
    assert client.get("/api/inventory", headers=cust).status_code == 403
    me = client.get("/api/auth/me", headers=cust).json()
    assert me["role"] == "CUSTOMER" and me["permissions"] == ["CATALOG_READ", "ORDER_PLACE", "ORDER_READ_OWN"]


def test_admin_manages_users_and_guards(client):
    admin = auth(client, "admin@test.com", "admin123")
    r = client.post("/api/users", json={"name": "Wh", "email": "WH@test.com", "password": "password1",
                                        "profiles": ["WAREHOUSE_STAFF"]}, headers=admin)
    assert r.status_code == 201 and r.json()["email"] == "wh@test.com" and r.json()["profiles"] == ["WAREHOUSE_STAFF"]
    uid = r.json()["id"]
    r = client.put(f"/api/users/{uid}/profiles", json={"profiles": ["STORE_MANAGER"]}, headers=admin)
    assert r.json()["profiles"] == ["STORE_MANAGER"] and "REPORT_DOWNLOAD" in r.json()["permissions"]
    assert client.patch(f"/api/users/{uid}/status", json={"status": "DISABLED"}, headers=admin).status_code == 200
    assert client.post("/api/auth/login", json={"email": "wh@test.com", "password": "password1"}).status_code == 403
    # an admin can't lock themselves out
    assert client.put("/api/users/1/profiles", json={"profiles": ["CUSTOMER"]}, headers=admin).status_code == 403
    assert client.patch("/api/users/1/status", json={"status": "DISABLED"}, headers=admin).status_code == 403
    matrix = {p["code"]: p for p in client.get("/api/access/profiles", headers=admin).json()}
    assert matrix["CUSTOMER"]["permissions"] == ["CATALOG_READ", "ORDER_PLACE", "ORDER_READ_OWN"]
    assert len(client.get("/api/access/permissions", headers=admin).json()) == 12


def test_registration_creates_customer_profile(client):
    outlet = client.post("/api/outlets", json={"name": "Pune East", "city": "Pune"},
                         headers=auth(client, "admin@test.com", "admin123")).json()
    cust = register(client, phone="9876500000", address_line="1 Lane", city="Pune", state="Maharashtra",
                    pincode="411001", preferred_outlet_id=outlet["id"])
    me = client.get("/api/auth/me", headers=cust).json()
    assert (me["phone"], me["city"], me["pincode"], me["preferred_outlet_id"]) == ("9876500000", "Pune", "411001", outlet["id"])
    dup = client.post("/api/auth/register", json={"name": "Two", "email": "two@test.com", "password": "secret12",
                                                  "phone": "9876500000"})
    assert dup.status_code == 409 and dup.json()["detail"] == "This phone number is already registered"
    assert client.post("/api/auth/register", json={"name": "Bad", "email": "b@test.com", "password": "secret12",
                                                   "pincode": "12"}).status_code == 422
    r = client.put("/api/auth/me", json={"name": "Cust Renamed", "city": "Mumbai", "pincode": "400001"}, headers=cust)
    assert r.json()["name"] == "Cust Renamed" and r.json()["city"] == "Mumbai"


# ------------------------------------------------------------------ orders, payments, delivery
def test_full_purchase_flow(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = register(client)

    # Over-ordering is rejected and nothing is deducted
    r = _order(client, cust, outlet, product, 11)
    assert r.status_code == 409 and "available: 10" in r.json()["detail"]
    r = _order(client, cust, outlet, product, 8)
    assert r.status_code == 201
    order = r.json()
    assert order["total_amount"] == 800 and order["payment"]["status"] == "PENDING"
    assert client.get(f"/api/products/{product['id']}", headers=cust).json()["total_stock"] == 2

    low = client.get("/api/inventory/low-stock", headers=admin).json()
    assert [row["product_id"] for row in low] == [product["id"]]

    # Declined then successful payment
    r = client.post(f"/api/orders/{order['id']}/pay", json={"method": "CARD", "card_number": "4111 1111 1111 0000"},
                    headers=cust)
    assert r.status_code == 402
    assert client.get(f"/api/orders/{order['id']}", headers=cust).json()["payment"]["status"] == "FAILED"
    r = client.post(f"/api/orders/{order['id']}/pay", json={"method": "UPI", "upi_id": "cust@okbank"}, headers=cust)
    assert r.status_code == 200 and r.json()["status"] == "PAID"
    assert r.json()["payment"]["transaction_ref"].startswith("TXN-") and r.json()["delivery"]["status"] == "PACKED"
    mine = client.get("/api/orders/my", headers=cust).json()
    assert [o["id"] for o in mine] == [order["id"]] and mine[0]["items"][0]["quantity"] == 8

    r = client.patch(f"/api/orders/{order['id']}/delivery", json={"status": "SHIPPED", "courier": "BlueDart",
                                                                  "tracking_number": "BD1"}, headers=admin)
    assert r.json()["delivery"]["status"] == "SHIPPED"
    assert client.post(f"/api/orders/{order['id']}/cancel", headers=cust).status_code == 409

    year = order["created_at"][:4]
    month = int(order["created_at"][5:7])
    rep = client.get(f"/api/reports/quarterly?year={year}&quarter={(month - 1) // 3 + 1}", headers=admin).json()
    assert rep["summary"] == {"orders": 1, "units_sold": 8, "revenue": 800.0}
    xl = client.get(f"/api/reports/quarterly/export?year={year}&quarter=1&format=xlsx", headers=admin)
    assert xl.status_code == 200 and xl.content[:2] == b"PK"


def test_cancel_returns_stock(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    oid = _order(client, admin, outlet, product, 4).json()["id"]
    r = client.post(f"/api/orders/{oid}/cancel", headers=admin)
    assert r.json()["status"] == "CANCELLED"
    rows = client.get(f"/api/inventory?outlet_id={outlet['id']}", headers=admin).json()
    assert rows[0]["quantity"] == 10
    log = client.get("/api/inventory/movements", headers=admin).json()
    assert [m["movement_type"] for m in log] == ["CANCEL", "SALE", "RESTOCK"]
    assert log[0]["changed_by"] == "Admin"


def test_transfer(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    o2 = client.post("/api/outlets", json={"name": "Second", "city": "Pune"}, headers=admin).json()
    r = client.post("/api/inventory/transfer", json={"product_id": product["id"], "from_outlet_id": outlet["id"],
                                                     "to_outlet_id": o2["id"], "quantity": 3}, headers=admin)
    assert r.json() == {"from_quantity": 7, "to_quantity": 3}
    too_many = client.post("/api/inventory/transfer", json={"product_id": product["id"], "from_outlet_id": outlet["id"],
                                                            "to_outlet_id": o2["id"], "quantity": 8}, headers=admin)
    assert too_many.status_code == 409                       # nothing moved: both outlets unchanged
    assert {r["outlet_id"]: r["quantity"] for r in client.get("/api/inventory", headers=admin).json()} == \
        {outlet["id"]: 7, o2["id"]: 3}


def test_oracle_trigger_logs_direct_sql_changes(client):
    """A plain UPDATE typed in SQL Developer is still recorded by TRG_INVENTORY_AUDIT."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE inventory SET quantity = quantity - 1 WHERE product_id = :p", {"p": product["id"]})
    conn.commit()
    conn.close()
    latest = client.get("/api/inventory/movements", headers=admin).json()[0]
    assert latest["movement_type"] == "MANUAL" and latest["change"] == -1


def test_validation_and_oracle_errors_become_http_errors(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    same = client.post("/api/inventory/transfer", json={"product_id": product["id"], "from_outlet_id": outlet["id"],
                                                        "to_outlet_id": outlet["id"], "quantity": 1}, headers=admin)
    assert same.status_code == 422 and same.json()["detail"] == "Choose two different outlets"
    missing = client.post("/api/inventory/restock", json={"product_id": 9999, "outlet_id": outlet["id"],
                                                          "quantity": 1}, headers=admin)
    assert missing.status_code == 404
    dup = client.post("/api/products", json={"sku": "t-1", "name": "Duplicate", "price": 1}, headers=admin)
    assert dup.status_code == 409
    assert client.post("/api/products", json={"sku": "JS", "name": "Bad image", "price": 1,
                                              "image_url": "javascript:alert(1)"}, headers=admin).status_code == 422
    assert client.get("/api/orders?sort=drop_table", headers=admin).status_code == 422


def test_survives_package_recompile(client):
    """Re-running 02_inventory_pkg.sql while the API is running must not break requests."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)          # API sessions now hold package state
    conn = connect()
    run_file(conn, SQL_DIR / "02_inventory_pkg.sql")
    conn.close()
    r = client.post("/api/inventory/restock", json={"product_id": product["id"], "outlet_id": outlet["id"],
                                                    "quantity": 5}, headers=admin)
    assert r.status_code == 200 and r.json()["quantity"] == 15


def test_health_checks_oracle(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["oracle_version"][:2].isdigit()


def test_sorting_and_latest_updated_filter(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = register(client)
    first = _order(client, cust, outlet, product, 1).json()["id"]
    second = _order(client, cust, outlet, product, 1).json()["id"]
    client.post(f"/api/orders/{first}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust)  # first changed last
    by_update = [o["id"] for o in client.get("/api/orders/my?sort=updated_desc", headers=cust).json()]
    by_created = [o["id"] for o in client.get("/api/orders/my?sort=created_desc", headers=cust).json()]
    assert by_update == [first, second] and by_created == [second, first]
    assert len(client.get("/api/orders?updated_within_days=1", headers=admin).json()) == 2
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE orders SET updated_at = SYSTIMESTAMP - INTERVAL '10' DAY WHERE order_id = :o", {"o": second})
    conn.commit()
    conn.close()
    assert [o["id"] for o in client.get("/api/orders?updated_within_days=7", headers=admin).json()] == [first]
    stock = client.get("/api/inventory?sort=quantity_asc", headers=admin).json()
    assert stock[0]["product_id"] == product["id"]


# ------------------------------------------------------------------ edge cases
def test_two_buyers_cannot_both_get_the_last_units(client):
    """Row locking (SELECT ... FOR UPDATE): 8 simultaneous buyers want 4 each of 10 in stock."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    results, barrier = [], threading.Barrier(8)
    buyer = {"id": 1}
    order = OrderIn(outlet_id=outlet["id"], shipping_address="1 Test Street",
                    items=[{"product_id": product["id"], "quantity": 4}])

    def buy():
        conn = connect()
        barrier.wait()
        try:
            order_service.place_order(conn, buyer, order)
            results.append("ok")
        except BusinessError as e:
            results.append(e.status)
        conn.close()

    threads = [threading.Thread(target=buy) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 2 and results.count(409) == 6       # 2 x 4 = 8 sold, never more than 10
    rows = client.get(f"/api/inventory?outlet_id={outlet['id']}", headers=admin).json()
    assert rows[0]["quantity"] == 2


def test_customers_cannot_see_or_touch_other_customers_orders(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    alice, bob = register(client, "alice@test.com"), register(client, "bob@test.com")
    oid = _order(client, alice, outlet, product, 1).json()["id"]
    assert client.get(f"/api/orders/{oid}", headers=bob).status_code == 403
    assert client.post(f"/api/orders/{oid}/cancel", headers=bob).status_code == 403
    assert client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "b@ok"}, headers=bob).status_code == 403
    assert client.get("/api/orders", headers=bob).status_code == 403


def test_cancelled_unpaid_order_and_payment_rules(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = register(client)
    oid = _order(client, cust, outlet, product, 3).json()["id"]
    cancelled = client.post(f"/api/orders/{oid}/cancel", headers=cust).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["payment"]["status"] == "CANCELLED"          # nothing left "waiting for payment"
    assert client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust).status_code == 409
    assert client.patch(f"/api/orders/{oid}/delivery", json={"status": "SHIPPED"}, headers=admin).status_code == 409


def test_delivery_cannot_go_backwards(client):
    """A delivered order can't be moved back to PACKED (which would allow cancelling it)."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = register(client)
    oid = _order(client, cust, outlet, product, 1).json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust)
    assert client.patch(f"/api/orders/{oid}/delivery", json={"status": "DELIVERED"}, headers=admin).status_code == 200
    assert client.patch(f"/api/orders/{oid}/delivery", json={"status": "PACKED"}, headers=admin).status_code == 409
    assert client.post(f"/api/orders/{oid}/cancel", headers=cust).status_code == 409


def test_hidden_product_cannot_be_ordered(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    client.delete(f"/api/products/{product['id']}", headers=admin)
    cust = register(client)
    assert _order(client, cust, outlet, product, 1).status_code == 404
    assert client.get("/api/products?include_inactive=true", headers=cust).json() == []   # customers can't list hidden


def test_return_restocks_and_refunds(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = register(client)
    oid = _order(client, cust, outlet, product, 4).json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust)
    early = client.patch(f"/api/orders/{oid}/delivery", json={"status": "RETURNED"}, headers=admin)
    assert early.status_code == 409                       # not shipped yet -> must be cancelled instead
    client.patch(f"/api/orders/{oid}/delivery", json={"status": "SHIPPED"}, headers=admin)
    r = client.patch(f"/api/orders/{oid}/delivery", json={"status": "RETURNED"}, headers=admin).json()
    assert r["status"] == "RETURNED" and r["payment"]["status"] == "REFUNDED"
    assert client.get(f"/api/inventory?outlet_id={outlet['id']}", headers=admin).json()[0]["quantity"] == 10
    assert client.get("/api/inventory/movements", headers=admin).json()[0]["movement_type"] == "RETURN"


def test_abandoned_checkout_releases_stock(client):
    """An order left unpaid for over 30 minutes is cancelled when the next order comes in,
    and paying it after the window is refused."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = register(client)
    stale = _order(client, cust, outlet, product, 9).json()["id"]          # holds 9 of 10
    assert _order(client, cust, outlet, product, 5).status_code == 409      # only 1 left
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE orders SET created_at = SYSTIMESTAMP - INTERVAL '31' MINUTE WHERE order_id = :o", {"o": stale})
    conn.commit()
    conn.close()
    late = client.post(f"/api/orders/{stale}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust)
    assert late.status_code == 409 and "payment window" in late.json()["detail"]
    old = client.get(f"/api/orders/{stale}", headers=cust).json()
    assert old["status"] == "CANCELLED" and old["payment"]["status"] == "CANCELLED"
    assert _order(client, cust, outlet, product, 5).status_code == 201      # the stock was released


def test_one_account_per_email_and_phone(client):
    """A customer can register only once: the email (any capitals) and the phone number are unique,
    checked in Python AND by Oracle's UNIQUE constraints; every user gets their own user_id."""
    first = client.post("/api/auth/register", json={"name": "Asha", "email": "asha@test.com", "password": "secret12",
                                                    "phone": "9811111111"})
    assert first.status_code == 201
    again = client.post("/api/auth/register", json={"name": "Asha Two", "email": "ASHA@Test.com", "password": "secret12"})
    assert again.status_code == 409 and again.json()["detail"] == "This email is already registered"
    phone = client.post("/api/auth/register", json={"name": "Other", "email": "other@test.com", "password": "secret12",
                                                    "phone": "9811111111"})
    assert phone.status_code == 409 and phone.json()["detail"] == "This phone number is already registered"
    admin = auth(client, "admin@test.com", "admin123")
    staff = client.post("/api/users", json={"name": "Xavier", "email": "asha@test.com", "password": "password1",
                                            "profiles": ["WAREHOUSE_STAFF"]}, headers=admin)
    assert staff.status_code == 409
    # and the database itself refuses a duplicate even if the application check were skipped
    conn = connect()
    with conn.cursor() as cur, pytest.raises(oracledb.IntegrityError):
        cur.execute("INSERT INTO users (full_name, email, password_hash) VALUES ('Dup', 'asha@test.com', 'x')")
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM users WHERE email = 'asha@test.com'")
        assert cur.fetchone() == (1, 1)
    conn.close()
