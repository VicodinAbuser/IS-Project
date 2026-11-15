"""Business rules for changing stock. Every change goes through change_stock() so the
inventory table and the stock_movements audit log always stay in sync."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Inventory, MovementType, Outlet, Product, StockMovement


def get_or_create_row(db: Session, product_id: int, outlet_id: int) -> Inventory:
    # with_for_update() locks the row on PostgreSQL so two buyers can't oversell the same item.
    row = db.scalar(
        select(Inventory)
        .where(Inventory.product_id == product_id, Inventory.outlet_id == outlet_id)
        .with_for_update()
    )
    if row is None:
        if db.get(Product, product_id) is None:
            raise HTTPException(404, f"Product {product_id} not found")
        if db.get(Outlet, outlet_id) is None:
            raise HTTPException(404, f"Outlet {outlet_id} not found")
        row = Inventory(product_id=product_id, outlet_id=outlet_id, quantity=0)
        db.add(row)
        db.flush()
    return row


def change_stock(db: Session, *, product_id: int, outlet_id: int, change: int,
                 movement_type: MovementType, user_id: int | None = None,
                 order_id: int | None = None, note: str | None = None) -> Inventory:
    """Add (change > 0) or remove (change < 0) stock. Caller commits the transaction."""
    row = get_or_create_row(db, product_id, outlet_id)
    if row.quantity + change < 0:
        product = db.get(Product, product_id)
        raise HTTPException(
            409, f"Not enough stock for '{product.name}' at this outlet (available: {row.quantity})"
        )
    row.quantity += change
    db.add(StockMovement(product_id=product_id, outlet_id=outlet_id, change=change,
                         movement_type=movement_type, user_id=user_id,
                         order_id=order_id, note=note))
    return row
