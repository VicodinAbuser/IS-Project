"""API tests against a real Oracle database.

They use a SEPARATE schema (default INVENTORY_TEST, created by database/00_create_user.sql)
and rebuild it before each test, so your demo data in INVENTORY is never touched.
Run: pytest -q
"""
import os

os.environ["ORACLE_USER"] = os.getenv("TEST_ORACLE_USER", "inventory_test")
os.environ["ORACLE_PASSWORD"] = os.getenv("TEST_ORACLE_PASSWORD", "inventory123")

import oracledb
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import hash_password
from setup_db import SQL_DIR, run_file


@pytest.fixture()
def client():
    conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    for name in ("01_schema.sql", "02_inventory_pkg.sql"):
        run_file(conn, SQL_DIR / name)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO app_users (full_name, email, password_hash, user_role)
                       VALUES ('Admin', 'admin@test.com', :h, 'ADMIN')""", {"h": hash_password("admin123")})
    conn.commit()
    conn.close()
    with TestClient(app) as c:
        yield c


def auth(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def setup_catalog(client, admin):
    outlet = client.post("/api/outlets", json={"name": "Test Outlet", "city": "Mumbai"}, headers=admin).json()
    product = client.post("/api/products", json={"sku": "T-1", "name": "Test Item", "price": 100,
                                                  "reorder_level": 3}, headers=admin).json()
    r = client.post("/api/inventory/restock", json={"product_id": product["id"], "outlet_id": outlet["id"],
                                                    "quantity": 10}, headers=admin)
    assert r.status_code == 200 and r.json()["quantity"] == 10
    return outlet, product


def test_security_roles(client):
    assert client.get("/api/products").status_code == 401
    r = client.post("/api/auth/register", json={"name": "Cust", "email": "c@test.com", "password": "secret1"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "CUSTOMER"
    cust = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/inventory", headers=cust).status_code == 403
    assert client.post("/api/products", json={"sku": "X", "name": "Nope", "price": 1}, headers=cust).status_code == 403
    assert client.post("/api/auth/login", json={"email": "c@test.com", "password": "wrong"}).status_code == 401


def test_full_purchase_flow(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    client.post("/api/auth/register", json={"name": "Cust", "email": "c@test.com", "password": "secret1"})
    cust = auth(client, "c@test.com", "secret1")

    # Over-ordering is rejected and nothing is deducted
    r = client.post("/api/orders", json={"outlet_id": outlet["id"], "shipping_address": "1 Test Street",
                                         "items": [{"product_id": product["id"], "quantity": 11}]}, headers=cust)
    assert r.status_code == 409

    r = client.post("/api/orders", json={"outlet_id": outlet["id"], "shipping_address": "1 Test Street",
                                         "items": [{"product_id": product["id"], "quantity": 8}]}, headers=cust)
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
    r = client.post(f"/api/orders/{order['id']}/pay", json={"method": "UPI", "upi_id": "cust@okbank"}, headers=cust)
    assert r.status_code == 200 and r.json()["status"] == "PAID"
    mine = client.get("/api/orders/my", headers=cust).json()
    assert [o["id"] for o in mine] == [order["id"]] and mine[0]["items"][0]["quantity"] == 8
    assert r.json()["payment"]["transaction_ref"].startswith("TXN-")

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
    r = client.post("/api/orders", json={"outlet_id": outlet["id"], "shipping_address": "1 Test Street",
                                         "items": [{"product_id": product["id"], "quantity": 4}]}, headers=admin)
    oid = r.json()["id"]
    r = client.post(f"/api/orders/{oid}/cancel", headers=admin)
    assert r.json()["status"] == "CANCELLED"
    rows = client.get(f"/api/inventory?outlet_id={outlet['id']}", headers=admin).json()
    assert rows[0]["quantity"] == 10
    types = [m["movement_type"] for m in client.get("/api/inventory/movements", headers=admin).json()]
    assert types == ["CANCEL", "SALE", "RESTOCK"]


def test_transfer(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    o2 = client.post("/api/outlets", json={"name": "Second", "city": "Pune"}, headers=admin).json()
    r = client.post("/api/inventory/transfer", json={"product_id": product["id"], "from_outlet_id": outlet["id"],
                                                     "to_outlet_id": o2["id"], "quantity": 3}, headers=admin)
    assert r.json() == {"from_quantity": 7, "to_quantity": 3}


def test_oracle_trigger_logs_direct_sql_changes(client):
    """A plain UPDATE typed in SQL Developer is still recorded by TRG_INVENTORY_AUDIT."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    with conn.cursor() as cur:
        cur.execute("UPDATE inventory SET quantity = quantity - 1 WHERE product_id = :p", {"p": product["id"]})
    conn.commit()
    conn.close()
    latest = client.get("/api/inventory/movements", headers=admin).json()[0]
    assert latest["movement_type"] == "MANUAL" and latest["change"] == -1


def test_plsql_errors_become_http_errors(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    same = client.post("/api/inventory/transfer", json={"product_id": product["id"], "from_outlet_id": outlet["id"],
                                                        "to_outlet_id": outlet["id"], "quantity": 1}, headers=admin)
    assert same.status_code == 422 and same.json()["detail"] == "Choose two different outlets"
    missing = client.post("/api/inventory/restock", json={"product_id": 9999, "outlet_id": outlet["id"],
                                                          "quantity": 1}, headers=admin)
    assert missing.status_code == 404
    dup = client.post("/api/products", json={"sku": "T-1", "name": "Duplicate", "price": 1}, headers=admin)
    assert dup.status_code == 409


def test_survives_package_recompile(client):
    """Re-running 02_inventory_pkg.sql while the API is running must not break requests."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)          # API sessions now hold package state
    conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    run_file(conn, SQL_DIR / "02_inventory_pkg.sql")
    conn.close()
    r = client.post("/api/inventory/restock", json={"product_id": product["id"], "outlet_id": outlet["id"],
                                                    "quantity": 5}, headers=admin)
    assert r.status_code == 200 and r.json()["quantity"] == 15


def test_health_checks_oracle(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["oracle_version"].startswith("23.")


# ---------------------------------------------------------------- edge cases
def _customer(client, email="c@test.com"):
    client.post("/api/auth/register", json={"name": "Cust", "email": email, "password": "secret1"})
    return auth(client, email, "secret1")


def _order(client, headers, outlet, product, qty):
    return client.post("/api/orders", json={"outlet_id": outlet["id"], "shipping_address": "1 Test Street",
                                            "items": [{"product_id": product["id"], "quantity": qty}]}, headers=headers)


def test_two_buyers_cannot_both_get_the_last_units(client):
    """Row locking (SELECT ... FOR UPDATE): 8 simultaneous buyers want 4 each of 10 in stock."""
    import threading
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    results, barrier = [], threading.Barrier(8)

    def buy():
        conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
        cur = conn.cursor()
        out = cur.var(oracledb.DB_TYPE_NUMBER)
        barrier.wait()
        try:
            cur.callproc("inventory_pkg.place_order", [1, outlet["id"], "1 Test Street",
                                                       f'[{{"product_id":{product["id"]},"quantity":4}}]', out])
            results.append("ok")
        except oracledb.DatabaseError as e:
            results.append(e.args[0].code)
        conn.close()

    threads = [threading.Thread(target=buy) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count("ok") == 2 and results.count(20001) == 6       # 2 x 4 = 8 sold, never more than 10
    rows = client.get(f"/api/inventory?outlet_id={outlet['id']}", headers=admin).json()
    assert rows[0]["quantity"] == 2


def test_customers_cannot_see_or_touch_other_customers_orders(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    alice, bob = _customer(client, "alice@test.com"), _customer(client, "bob@test.com")
    oid = _order(client, alice, outlet, product, 1).json()["id"]
    assert client.get(f"/api/orders/{oid}", headers=bob).status_code == 403
    assert client.post(f"/api/orders/{oid}/cancel", headers=bob).status_code == 403
    assert client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "b@ok"}, headers=bob).status_code == 403
    assert client.get("/api/orders", headers=bob).status_code == 403


def test_cancelled_unpaid_order_and_payment_rules(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = _customer(client)
    oid = _order(client, cust, outlet, product, 3).json()["id"]
    cancelled = client.post(f"/api/orders/{oid}/cancel", headers=cust).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["payment"]["status"] != "PENDING"          # nothing left "waiting for payment"
    assert client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust).status_code == 409
    assert client.patch(f"/api/orders/{oid}/delivery", json={"status": "SHIPPED"}, headers=admin).status_code == 409


def test_delivery_cannot_go_backwards(client):
    """A delivered order can't be moved back to PACKED (which would allow cancelling it)."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = _customer(client)
    oid = _order(client, cust, outlet, product, 1).json()["id"]
    client.post(f"/api/orders/{oid}/pay", json={"method": "UPI", "upi_id": "c@ok"}, headers=cust)
    assert client.patch(f"/api/orders/{oid}/delivery", json={"status": "DELIVERED"}, headers=admin).status_code == 200
    assert client.patch(f"/api/orders/{oid}/delivery", json={"status": "PACKED"}, headers=admin).status_code == 409
    assert client.post(f"/api/orders/{oid}/cancel", headers=cust).status_code == 409


def test_hidden_product_cannot_be_ordered(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    client.delete(f"/api/products/{product['id']}", headers=admin)
    assert _order(client, _customer(client), outlet, product, 1).status_code == 404


def test_return_restocks_and_refunds(client):
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = _customer(client)
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
    """An order left unpaid for over 30 minutes is cancelled when the next order comes in."""
    admin = auth(client, "admin@test.com", "admin123")
    outlet, product = setup_catalog(client, admin)
    cust = _customer(client)
    stale = _order(client, cust, outlet, product, 9).json()["id"]          # holds 9 of 10
    assert _order(client, cust, outlet, product, 5).status_code == 409      # only 1 left
    conn = oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn)
    with conn.cursor() as cur:
        cur.execute("UPDATE orders SET created_at = SYSTIMESTAMP - INTERVAL '31' MINUTE WHERE order_id = :o", {"o": stale})
    conn.commit()
    conn.close()
    assert _order(client, cust, outlet, product, 5).status_code == 201      # stale order released its stock
    old = client.get(f"/api/orders/{stale}", headers=cust).json()
    assert old["status"] == "CANCELLED" and old["payment"]["status"] == "CANCELLED"
