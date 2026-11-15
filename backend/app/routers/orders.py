"""Orders, payments (demo gateway) and delivery tracking."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..inventory_service import change_stock
from ..models import (Delivery, DeliveryStatus, MovementType, Order, OrderItem, OrderStatus, Outlet,
                      Payment, PaymentStatus, Product, Role, User)
from ..schemas import DeliveryUpdateIn, OrderIn, OrderOut, PaymentIn
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/orders", tags=["Orders, payments & delivery"])

LOAD = (selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.outlet),
        selectinload(Order.customer), selectinload(Order.payment), selectinload(Order.delivery))


def _get_order(db: Session, order_id: int, user: User) -> Order:
    order = db.scalar(select(Order).options(*LOAD).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "Order not found")
    if user.role != Role.ADMIN and order.customer_id != user.id:
        raise HTTPException(403, "Not your order")  # customers only see their own orders
    return order


@router.post("", response_model=OrderOut, status_code=201)
def place_order(data: OrderIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Customer checkout. Stock is reserved (deducted) immediately so it can't be oversold;
    it is returned automatically if the order is cancelled."""
    if not db.get(Outlet, data.outlet_id):
        raise HTTPException(404, "Outlet not found")
    order = Order(customer_id=user.id, outlet_id=data.outlet_id, total_amount=0,
                  shipping_address=data.shipping_address)
    db.add(order)
    db.flush()  # get order.id

    total = 0.0
    merged: dict[int, int] = {}
    for item in data.items:
        merged[item.product_id] = merged.get(item.product_id, 0) + item.quantity
    for product_id, qty in merged.items():
        product = db.get(Product, product_id)
        if not product or not product.is_active:
            db.rollback()
            raise HTTPException(404, f"Product {product_id} not available")
        try:
            change_stock(db, product_id=product_id, outlet_id=data.outlet_id, change=-qty,
                         movement_type=MovementType.SALE, user_id=user.id, order_id=order.id)
        except HTTPException:
            db.rollback()  # undo everything in this order — all-or-nothing
            raise
        db.add(OrderItem(order_id=order.id, product_id=product_id, quantity=qty, unit_price=product.price))
        total += float(product.price) * qty

    order.total_amount = round(total, 2)
    db.add(Payment(order_id=order.id, amount=order.total_amount, status=PaymentStatus.PENDING))
    db.add(Delivery(order_id=order.id, status=DeliveryStatus.NOT_SHIPPED))
    db.commit()
    return _get_order(db, order.id, user)


@router.get("/my", response_model=list[OrderOut])
def my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Order).options(*LOAD).where(Order.customer_id == user.id)
                      .order_by(Order.created_at.desc())).all()


@router.get("", response_model=list[OrderOut])
def all_orders(status: OrderStatus | None = None, outlet_id: int | None = None,
               delivery_status: DeliveryStatus | None = None, limit: int = Query(200, le=1000),
               db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = select(Order).options(*LOAD).order_by(Order.created_at.desc()).limit(limit)
    if status:
        q = q.where(Order.status == status)
    if outlet_id:
        q = q.where(Order.outlet_id == outlet_id)
    if delivery_status:
        q = q.join(Delivery).where(Delivery.status == delivery_status)
    return db.scalars(q).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_order(db, order_id, user)


@router.post("/{order_id}/pay", response_model=OrderOut)
def pay(order_id: int, data: PaymentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Demo payment gateway. In production this would call Razorpay/Stripe and verify
    their signed webhook. Test rule: card ending in 0000 or UPI id starting with 'fail' is declined."""
    order = _get_order(db, order_id, user)
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise HTTPException(409, f"Order is {order.status.value}, cannot pay")
    declined = (data.method == "CARD" and (data.card_number or "").replace(" ", "").endswith("0000")) or \
               (data.method == "UPI" and (data.upi_id or "").lower().startswith("fail"))
    pay_row = order.payment
    pay_row.method = data.method
    if declined:
        pay_row.status = PaymentStatus.FAILED  # order stays PENDING_PAYMENT so the customer can retry
    else:
        pay_row.status = PaymentStatus.SUCCESS
        pay_row.transaction_ref = "TXN-" + uuid.uuid4().hex[:12].upper()
        order.status = OrderStatus.PAID
        order.delivery.status = DeliveryStatus.PACKED
    db.commit()
    if declined:
        raise HTTPException(402, "Payment declined by bank. Please try another method.")
    return _get_order(db, order_id, user)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cancel before shipping: stock goes back to the outlet and a paid order is refunded."""
    order = _get_order(db, order_id, user)
    if order.status == OrderStatus.CANCELLED:
        raise HTTPException(409, "Order already cancelled")
    if order.delivery.status not in (DeliveryStatus.NOT_SHIPPED, DeliveryStatus.PACKED):
        raise HTTPException(409, "Order already shipped, cannot cancel")
    for item in order.items:
        change_stock(db, product_id=item.product_id, outlet_id=order.outlet_id, change=item.quantity,
                     movement_type=MovementType.CANCEL, user_id=user.id, order_id=order.id,
                     note=f"Order #{order.id} cancelled")
    if order.payment.status == PaymentStatus.SUCCESS:
        order.payment.status = PaymentStatus.REFUNDED
    order.status = OrderStatus.CANCELLED
    db.commit()
    return _get_order(db, order_id, user)


@router.patch("/{order_id}/delivery", response_model=OrderOut)
def update_delivery(order_id: int, data: DeliveryUpdateIn, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    order = _get_order(db, order_id, admin)
    if order.status != OrderStatus.PAID:
        raise HTTPException(409, "Only paid orders can be shipped")
    order.delivery.status = data.status
    if data.tracking_number is not None:
        order.delivery.tracking_number = data.tracking_number
    if data.courier is not None:
        order.delivery.courier = data.courier
    db.commit()
    return _get_order(db, order_id, admin)
