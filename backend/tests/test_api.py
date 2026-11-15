"""API tests. Run: pytest -q"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_inventory.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Role, User
from app.security import hash_password


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(name="Admin", email="admin@test.com", password_hash=hash_password("admin123"), role=Role.ADMIN))
    db.commit()
    db.close()
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
