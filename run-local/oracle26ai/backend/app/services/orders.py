"""Business rules for orders, payments and deliveries.

Life of an order:
  place  -> order PENDING_PAYMENT, payment PENDING, delivery NOT_SHIPPED, stock taken (SALE)
  pay    -> order PAID, payment SUCCESS, delivery PACKED          (declined: payment FAILED, may retry)
  ship   -> delivery SHIPPED -> OUT_FOR_DELIVERY -> DELIVERED     (only forwards)
  cancel -> only before shipping: stock back (CANCEL), payment REFUNDED (if paid) or CANCELLED
  return -> only after shipping: stock back (RETURN), payment REFUNDED, order RETURNED
  expiry -> unpaid for longer than settings.payment_timeout_minutes: cancelled automatically
Each function below is ONE transaction: everything happens, or nothing does.
"""
from dataclasses import dataclass
from datetime import datetime

import oracledb

from ..config import settings
from ..database import call_procedure, query, query_one, transaction
from ..errors import BusinessError, conflict, forbidden, invalid, not_found
from ..schemas import OrderIn
from ..security import Perm, has
from . import payment_gateway
from .inventory import take_stock

DELIVERY_STEPS = ["NOT_SHIPPED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]
SHIPPED = {"SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"}
CANCELLABLE = {"NOT_SHIPPED", "PACKED"}


@dataclass
class OrderState:
    order_id: int
    customer_id: int
    outlet_id: int
    status: str
    payment_status: str
    delivery_status: str
    created_at: datetime


def lock_order(db: oracledb.Connection, order_id: int) -> OrderState:
    r = call_procedure(db, "inventory_pkg.lock_order", p_order_id=order_id,
                       out={"p_customer_id": int, "p_outlet_id": int, "p_order_status": str,
                            "p_payment_status": str, "p_delivery_status": str, "p_created_at": datetime})
    return OrderState(order_id, r["p_customer_id"], r["p_outlet_id"], r["p_order_status"], r["p_payment_status"],
                      r["p_delivery_status"], r["p_created_at"])


def _must_be_allowed(user: dict, order: OrderState, manage_permission: str = Perm.ORDER_MANAGE) -> None:
    """Customers may act on their own orders; staff need the management permission."""
    if order.customer_id != user["id"] and not has(user, manage_permission):
        raise forbidden("Not your order")


def _is_expired(db: oracledb.Connection, order: OrderState) -> bool:
    """Unpaid for longer than the payment window? (Measured with the database clock.)"""
    if order.status != "PENDING_PAYMENT":
        return False
    return query_one(db, """SELECT CASE WHEN :created < CAST(SYSTIMESTAMP AS TIMESTAMP) - NUMTODSINTERVAL(:mins, 'MINUTE')
                                     THEN 1 ELSE 0 END AS expired FROM dual""",
                     {"created": order.created_at, "mins": settings.payment_timeout_minutes})["expired"] == 1


def _undo(db: oracledb.Connection, order: OrderState, user_id: int | None, note: str) -> None:
    """Cancel an unshipped order: stock back, payment refunded or closed, order CANCELLED."""
    call_procedure(db, "inventory_pkg.restore_order_stock", p_order_id=order.order_id, p_movement_type="CANCEL",
                   p_user_id=user_id, p_note=note)
    paid = order.payment_status == "SUCCESS"
    call_procedure(db, "inventory_pkg.set_payment", p_order_id=order.order_id,
                   p_status="REFUNDED" if paid else "CANCELLED")
    call_procedure(db, "inventory_pkg.set_order_status", p_order_id=order.order_id, p_status="CANCELLED")


def expire_unpaid_orders(db: oracledb.Connection) -> int:
    """Cancels orders left unpaid too long, giving their stock back. Runs inside the caller's
    transaction. SKIP LOCKED: an order someone is paying for right now is left alone."""
    stale = query(db, """SELECT order_id FROM orders
                          WHERE order_status = 'PENDING_PAYMENT'
                            AND created_at < CAST(SYSTIMESTAMP AS TIMESTAMP) - NUMTODSINTERVAL(:mins, 'MINUTE')
                          ORDER BY order_id
                            FOR UPDATE SKIP LOCKED""", {"mins": settings.payment_timeout_minutes})
    for row in stale:
        order = lock_order(db, row["order_id"])
        _undo(db, order, None,
              f"Order #{order.order_id} not paid within {settings.payment_timeout_minutes} minutes")
    return len(stale)


def place_order(db: oracledb.Connection, user: dict, data: OrderIn) -> int:
    # Merge duplicate lines and work in product order, so two orders lock rows in the same order (no deadlocks).
    wanted: dict[int, int] = {}
    for item in data.items:
        wanted[item.product_id] = wanted.get(item.product_id, 0) + item.quantity
    if len(wanted) > settings.max_items_per_order:
        raise invalid(f"An order can contain at most {settings.max_items_per_order} different products")
    address = data.shipping_address.strip()
    if len(address) < 5:
        raise invalid("Shipping address is too short")

    def work():
        if not query_one(db, "SELECT 1 AS ok FROM outlets WHERE outlet_id = :id", {"id": data.outlet_id}):
            raise not_found("Outlet")
        expire_unpaid_orders(db)                      # release stock held by abandoned checkouts first
        order_id = call_procedure(db, "inventory_pkg.create_order", out={"p_order_id": int},
                                  p_customer_id=user["id"], p_outlet_id=data.outlet_id,
                                  p_shipping_address=address)["p_order_id"]
        total = 0.0
        for product_id in sorted(wanted):
            qty = wanted[product_id]
            product = query_one(db, "SELECT product_id, name, price, is_active FROM products WHERE product_id = :id",
                                {"id": product_id})
            if not product or not product["is_active"]:
                raise not_found(f"Product {product_id}")
            take_stock(db, product, data.outlet_id, qty, "SALE", user["id"], order_id, f"Order #{order_id}")
            # The price is copied into the order, so later price changes don't alter it.
            call_procedure(db, "inventory_pkg.add_order_item", p_order_id=order_id, p_product_id=product_id,
                           p_quantity=qty, p_unit_price=product["price"])
            total += float(product["price"]) * qty
        call_procedure(db, "inventory_pkg.open_payment_and_delivery", p_order_id=order_id,
                       p_total_amount=round(total, 2))
        return order_id
    return transaction(db, work)


def pay(db: oracledb.Connection, user: dict, order_id: int, method: str, card_number: str | None,
        upi_id: str | None) -> None:
    def work():
        order = lock_order(db, order_id)
        _must_be_allowed(user, order, Perm.ORDER_MANAGE)
        if order.status != "PENDING_PAYMENT":
            raise conflict(f"Order is {order.status}, cannot pay")
        if _is_expired(db, order):
            _undo(db, order, None, f"Order #{order_id} not paid within {settings.payment_timeout_minutes} minutes")
            return BusinessError(409, f"The payment window of {settings.payment_timeout_minutes} minutes has "
                                      "passed, so the order was cancelled and the items released.")
        amount = query_one(db, "SELECT amount FROM payments WHERE order_id = :id", {"id": order_id})["amount"]
        result = payment_gateway.charge(method, float(amount), card_number, upi_id)
        if not result.approved:
            # Declined: keep the order open so the customer can try again.
            call_procedure(db, "inventory_pkg.set_payment", p_order_id=order_id, p_status="FAILED", p_method=method)
            return BusinessError(402, result.message)
        call_procedure(db, "inventory_pkg.set_payment", p_order_id=order_id, p_status="SUCCESS", p_method=method,
                       p_transaction_ref=result.transaction_ref)
        call_procedure(db, "inventory_pkg.set_order_status", p_order_id=order_id, p_status="PAID")
        call_procedure(db, "inventory_pkg.set_delivery", p_order_id=order_id, p_status="PACKED")
        return None
    # A declined or expired payment is still saved (committed), then reported as an error.
    problem = transaction(db, work)
    if problem:
        raise problem


def cancel(db: oracledb.Connection, user: dict, order_id: int) -> None:
    def work():
        order = lock_order(db, order_id)
        _must_be_allowed(user, order)
        if order.status in ("CANCELLED", "RETURNED"):
            raise conflict(f"Order already {order.status.lower()}")
        if order.delivery_status not in CANCELLABLE:
            raise conflict("Order already shipped, cannot cancel (it can be returned after delivery)")
        _undo(db, order, user["id"], f"Order #{order_id} cancelled")
    transaction(db, work)


def update_delivery(db: oracledb.Connection, user: dict, order_id: int, status: str,
                    courier: str | None, tracking_number: str | None) -> None:
    def work():
        order = lock_order(db, order_id)
        if order.status != "PAID":
            raise conflict(f"Only paid orders can be shipped (this order is {order.status})")
        current = order.delivery_status
        if status == "RETURNED":
            if current not in SHIPPED:
                raise conflict("Only shipped orders can be returned; cancel it instead")
            call_procedure(db, "inventory_pkg.set_delivery", p_order_id=order_id, p_status="RETURNED")
            call_procedure(db, "inventory_pkg.restore_order_stock", p_order_id=order_id, p_movement_type="RETURN",
                           p_user_id=user["id"], p_note=f"Order #{order_id} returned")
            call_procedure(db, "inventory_pkg.set_payment", p_order_id=order_id, p_status="REFUNDED")
            call_procedure(db, "inventory_pkg.set_order_status", p_order_id=order_id, p_status="RETURNED")
            return
        if DELIVERY_STEPS.index(status) < DELIVERY_STEPS.index(current):
            raise conflict(f"Delivery cannot go back from {current} to {status}")
        # Shipping without a courier name means our own delivery van.
        carrier = courier or ("In-house delivery" if status in SHIPPED and current not in SHIPPED else None)
        call_procedure(db, "inventory_pkg.set_delivery", p_order_id=order_id, p_status=status,
                       p_courier=carrier, p_tracking_number=tracking_number)
    transaction(db, work)
