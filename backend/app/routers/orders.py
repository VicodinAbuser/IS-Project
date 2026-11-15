"""Orders, payments (demo gateway) and delivery tracking. The work is done by INVENTORY_PKG procedures."""
import json

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import call_procedure, get_db, query
from ..schemas import DeliveryStatus, DeliveryUpdateIn, OrderIn, OrderOut, OrderStatus, PaymentIn
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/orders", tags=["Orders, payments & delivery"])

ORDER_SELECT = """
    SELECT o.order_id, o.order_status, o.total_amount, o.shipping_address, o.created_at,
           ou.outlet_id, ou.name AS outlet_name, ou.city AS outlet_city, ou.address AS outlet_address,
           u.user_id AS customer_id, u.full_name AS customer_name, u.email AS customer_email,
           p.amount, p.payment_method, p.payment_status, p.transaction_ref, p.updated_at AS payment_updated,
           d.delivery_status, d.courier, d.tracking_number, d.updated_at AS delivery_updated
      FROM orders o
      JOIN outlets ou   ON ou.outlet_id = o.outlet_id
      JOIN app_users u  ON u.user_id    = o.customer_id
      LEFT JOIN payments p   ON p.order_id = o.order_id
      LEFT JOIN deliveries d ON d.order_id = o.order_id"""


def load_orders(db: oracledb.Connection, where: str = "", params: dict | None = None, limit: int = 1000) -> list[OrderOut]:
    rows = query(db, f"{ORDER_SELECT} {where} ORDER BY o.created_at DESC, o.order_id DESC FETCH FIRST {int(limit)} ROWS ONLY",
                 params)
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
        shipping_address=r["shipping_address"], created_at=r["created_at"],
        outlet={"id": r["outlet_id"], "name": r["outlet_name"], "city": r["outlet_city"], "address": r["outlet_address"]},
        customer={"id": r["customer_id"], "name": r["customer_name"], "email": r["customer_email"]},
        items=by_order.get(r["order_id"], []),
        payment={"amount": r["amount"], "method": r["payment_method"], "status": r["payment_status"],
                 "transaction_ref": r["transaction_ref"], "updated_at": r["payment_updated"]} if r["payment_status"] else None,
        delivery={"status": r["delivery_status"], "courier": r["courier"], "tracking_number": r["tracking_number"],
                  "updated_at": r["delivery_updated"]} if r["delivery_status"] else None,
    ) for r in rows]


def get_order_for(db: oracledb.Connection, order_id: int, user: dict) -> OrderOut:
    found = load_orders(db, "WHERE o.order_id = :id", {"id": order_id})
    if not found:
        raise HTTPException(404, "Order not found")
    if user["role"] != "ADMIN" and found[0].customer.id != user["id"]:
        raise HTTPException(403, "Not your order")      # customers only see their own orders
    return found[0]


@router.post("", response_model=OrderOut, status_code=201)
def place_order(data: OrderIn, db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    """Checkout. INVENTORY_PKG.PLACE_ORDER reserves the stock in one transaction (all items or none)."""
    result = call_procedure(db, "inventory_pkg.place_order", out_numbers=("p_order_id",),
                            p_customer_id=user["id"], p_outlet_id=data.outlet_id,
                            p_shipping_address=data.shipping_address,
                            p_items_json=json.dumps([i.model_dump() for i in data.items]))
    return get_order_for(db, int(result["p_order_id"]), user)


@router.get("/my", response_model=list[OrderOut])
def my_orders(db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    return load_orders(db, "WHERE o.customer_id = :customer_id", {"customer_id": user["id"]})


@router.get("", response_model=list[OrderOut])
def all_orders(status: OrderStatus | None = None, outlet_id: int | None = None,
               delivery_status: DeliveryStatus | None = None, limit: int = Query(200, le=1000),
               db: oracledb.Connection = Depends(get_db), _: dict = Depends(require_admin)):
    where, params = [], {}
    if status:
        where.append("o.order_status = :status")
        params["status"] = status.value
    if outlet_id:
        where.append("o.outlet_id = :outlet_id")
        params["outlet_id"] = outlet_id
    if delivery_status:
        where.append("d.delivery_status = :dstatus")
        params["dstatus"] = delivery_status.value
    return load_orders(db, ("WHERE " + " AND ".join(where)) if where else "", params, limit)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    return get_order_for(db, order_id, user)


@router.post("/{order_id}/pay", response_model=OrderOut)
def pay(order_id: int, data: PaymentIn, db: oracledb.Connection = Depends(get_db),
        user: dict = Depends(get_current_user)):
    """Demo payment gateway. A real gateway (Razorpay/Stripe) would decide success here; the result is
    then saved by INVENTORY_PKG.RECORD_PAYMENT. Test rule: card ending 0000 or UPI id starting 'fail' is declined."""
    get_order_for(db, order_id, user)                       # 404 / 403 checks
    declined = (data.method == "CARD" and (data.card_number or "").replace(" ", "").endswith("0000")) or \
               (data.method == "UPI" and (data.upi_id or "").lower().startswith("fail"))
    call_procedure(db, "inventory_pkg.record_payment",
                   p_order_id=order_id, p_method=data.method, p_success=0 if declined else 1)
    if declined:
        raise HTTPException(402, "Payment declined by bank. Please try another method.")
    return get_order_for(db, order_id, user)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: int, db: oracledb.Connection = Depends(get_db), user: dict = Depends(get_current_user)):
    """Cancel before shipping: INVENTORY_PKG.CANCEL_ORDER returns stock and refunds a paid order."""
    get_order_for(db, order_id, user)
    call_procedure(db, "inventory_pkg.cancel_order", p_order_id=order_id, p_user_id=user["id"])
    return get_order_for(db, order_id, user)


@router.patch("/{order_id}/delivery", response_model=OrderOut)
def update_delivery(order_id: int, data: DeliveryUpdateIn, db: oracledb.Connection = Depends(get_db),
                    admin: dict = Depends(require_admin)):
    get_order_for(db, order_id, admin)
    call_procedure(db, "inventory_pkg.update_delivery", p_order_id=order_id, p_status=data.status.value,
                   p_courier=data.courier, p_tracking_number=data.tracking_number)
    return get_order_for(db, order_id, admin)
