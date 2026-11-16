"""Orders, payments (demo gateway) and delivery tracking. The rules are in app/services/orders.py."""
import json

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db, query
from ..listing import UPDATED_WITHIN, order_by, updated_within, where_sql
from ..schemas import DeliveryStatus, DeliveryUpdateIn, OrderIn, OrderOut, OrderStatus, PaymentIn
from ..security import Perm, get_current_user, has, require
from ..services import orders

router = APIRouter(prefix="/api/orders", tags=["Orders, payments & delivery"])

ORDER_SELECT = """
    SELECT o.order_id, o.order_status, o.total_amount, o.shipping_address, o.created_at, o.updated_at,
           ou.outlet_id, ou.name AS outlet_name, ou.city AS outlet_city, ou.address AS outlet_address,
           u.user_id AS customer_id, u.full_name AS customer_name, u.email AS customer_email, cp.phone AS customer_phone,
           p.amount, p.payment_method, p.payment_status, p.transaction_ref, p.updated_at AS payment_updated,
           d.delivery_status, d.courier, d.tracking_number, d.updated_at AS delivery_updated
      FROM orders o
      JOIN outlets ou   ON ou.outlet_id = o.outlet_id
      JOIN users u      ON u.user_id    = o.customer_id
      LEFT JOIN customer_profiles cp ON cp.customer_id = o.customer_id
      LEFT JOIN payments p   ON p.order_id = o.order_id
      LEFT JOIN deliveries d ON d.order_id = o.order_id"""
ORDER_SORTS = {"updated_desc": "o.updated_at DESC", "updated_asc": "o.updated_at", "created_desc": "o.created_at DESC",
               "created_asc": "o.created_at", "amount_desc": "o.total_amount DESC", "amount_asc": "o.total_amount"}


def load_orders(db: oracledb.Connection, where: list[str], params: dict, sort: str | None = None,
                limit: int = 1000) -> list[OrderOut]:
    rows = query(db, ORDER_SELECT + where_sql(where) + order_by(sort, ORDER_SORTS, "updated_desc", "o.order_id DESC")
                 + f" FETCH FIRST {int(limit)} ROWS ONLY", params)
    if not rows:
        return []
    # Fetch all items for these orders in one query (order ids passed as a JSON array).
    items = query(db, """
        SELECT oi.order_id, oi.product_id, oi.quantity, oi.unit_price, pr.sku, pr.name
          FROM order_items oi JOIN products pr ON pr.product_id = oi.product_id
         WHERE oi.order_id IN (SELECT id FROM JSON_TABLE(:ids, '$[*]' COLUMNS (id NUMBER PATH '$')))
         ORDER BY oi.order_item_id""", {"ids": json.dumps([r["order_id"] for r in rows])})
    by_order: dict[int, list] = {}
    for i in items:
        by_order.setdefault(i["order_id"], []).append(
            {"product_id": i["product_id"], "quantity": i["quantity"], "unit_price": i["unit_price"],
             "product": {"id": i["product_id"], "sku": i["sku"], "name": i["name"]}})
    return [OrderOut(
        id=r["order_id"], status=r["order_status"], total_amount=r["total_amount"],
        shipping_address=r["shipping_address"], created_at=r["created_at"], updated_at=r["updated_at"],
        outlet={"id": r["outlet_id"], "name": r["outlet_name"], "city": r["outlet_city"], "address": r["outlet_address"]},
        customer={"id": r["customer_id"], "name": r["customer_name"], "email": r["customer_email"],
                  "phone": r["customer_phone"]},
        items=by_order.get(r["order_id"], []),
        payment={"amount": r["amount"], "method": r["payment_method"], "status": r["payment_status"],
                 "transaction_ref": r["transaction_ref"], "updated_at": r["payment_updated"]} if r["payment_status"] else None,
        delivery={"status": r["delivery_status"], "courier": r["courier"], "tracking_number": r["tracking_number"],
                  "updated_at": r["delivery_updated"]} if r["delivery_status"] else None,
    ) for r in rows]


def get_order_for(db: oracledb.Connection, order_id: int, user: dict) -> OrderOut:
    found = load_orders(db, ["o.order_id = :id"], {"id": order_id})
    if not found:
        raise HTTPException(404, "Order not found")
    if found[0].customer.id != user["id"] and not has(user, Perm.ORDER_READ_ALL):
        raise HTTPException(403, "Not your order")      # customers only see their own orders
    return found[0]


def _filters(status: OrderStatus | None, delivery_status: DeliveryStatus | None, days: int | None,
             where: list[str], params: dict) -> None:
    if status:
        where.append("o.order_status = :status")
        params["status"] = status.value
    if delivery_status:
        where.append("d.delivery_status = :dstatus")
        params["dstatus"] = delivery_status.value
    updated_within("o.updated_at", days, where, params)


@router.post("", response_model=OrderOut, status_code=201)
def place_order(data: OrderIn, db: oracledb.Connection = Depends(get_db), user: dict = Depends(require(Perm.ORDER_PLACE))):
    """Checkout: the stock is reserved in one transaction (all items or none)."""
    return get_order_for(db, orders.place_order(db, user, data), user)


@router.get("/my", response_model=list[OrderOut])
def my_orders(status: OrderStatus | None = None, sort: str | None = None,
              updated_within_days: int | None = UPDATED_WITHIN, limit: int = Query(200, ge=1, le=1000),
              db: oracledb.Connection = Depends(get_db), user: dict = Depends(require(Perm.ORDER_READ_OWN))):
    where, params = ["o.customer_id = :customer_id"], {"customer_id": user["id"]}
    _filters(status, None, updated_within_days, where, params)
    return load_orders(db, where, params, sort, limit)


@router.get("", response_model=list[OrderOut])
def all_orders(status: OrderStatus | None = None, outlet_id: int | None = None,
               delivery_status: DeliveryStatus | None = None, search: str | None = Query(None, max_length=100),
               sort: str | None = None, updated_within_days: int | None = UPDATED_WITHIN,
               limit: int = Query(100, ge=1, le=1000),
               db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.ORDER_READ_ALL))):
    where, params = [], {}
    _filters(status, delivery_status, updated_within_days, where, params)
    if outlet_id:
        where.append("o.outlet_id = :outlet_id")
        params["outlet_id"] = outlet_id
    if search:
        term = search.strip().lstrip("#")
        if term.isdigit():
            where.append("o.order_id = :order_no")
            params["order_no"] = int(term)
        else:
            where.append("(UPPER(u.full_name) LIKE UPPER(:q) OR u.email LIKE LOWER(:q))")
            params["q"] = f"%{term}%"
    return load_orders(db, where, params, sort, limit)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    return get_order_for(db, order_id, user)


@router.post("/{order_id}/pay", response_model=OrderOut)
def pay(order_id: int, data: PaymentIn, db: oracledb.Connection = Depends(get_db),
        user: dict = Depends(get_current_user)):
    """Demo payment gateway (see app/services/payment_gateway.py).
    Test rule: card ending 0000 or UPI id starting 'fail' is declined."""
    orders.pay(db, user, order_id, data.method, data.card_number, data.upi_id)
    return get_order_for(db, order_id, user)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: int, db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    """Cancel before shipping: stock goes back and a paid order is refunded."""
    orders.cancel(db, user, order_id)
    return get_order_for(db, order_id, user)


@router.patch("/{order_id}/delivery", response_model=OrderOut)
def update_delivery(order_id: int, data: DeliveryUpdateIn, db: oracledb.Connection = Depends(get_db),
                    user: dict = Depends(require(Perm.ORDER_MANAGE))):
    orders.update_delivery(db, user, order_id, data.status.value, data.courier, data.tracking_number)
    return get_order_for(db, order_id, user)
