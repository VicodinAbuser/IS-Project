"""Admin-only stock management: view stock, restock, adjust, transfer, audit log."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..inventory_service import change_stock
from ..models import Inventory, MovementType, Outlet, Product, StockMovement, User
from ..schemas import AdjustIn, InventoryRow, MovementOut, StockChangeIn, TransferIn
from ..security import require_admin

router = APIRouter(prefix="/api/inventory", tags=["Inventory (admin)"])


def _rows(db: Session, outlet_id: int | None = None, low_only: bool = False) -> list[InventoryRow]:
    q = (select(Inventory, Product, Outlet)
         .join(Product, Inventory.product_id == Product.id)
         .join(Outlet, Inventory.outlet_id == Outlet.id)
         .where(Product.is_active.is_(True))
         .order_by(Outlet.name, Product.name))
    if outlet_id:
        q = q.where(Inventory.outlet_id == outlet_id)
    if low_only:
        q = q.where(Inventory.quantity <= Product.reorder_level)
    return [InventoryRow(product_id=p.id, sku=p.sku, product_name=p.name, outlet_id=o.id,
                         outlet_name=o.name, quantity=i.quantity, reorder_level=p.reorder_level,
                         low_stock=i.quantity <= p.reorder_level)
            for i, p, o in db.execute(q).all()]


@router.get("", response_model=list[InventoryRow])
def stock_by_outlet(outlet_id: int | None = Query(None, description="Omit for all outlets"),
                    db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _rows(db, outlet_id)


@router.get("/low-stock", response_model=list[InventoryRow])
def low_stock(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _rows(db, low_only=True)


@router.get("/summary")
def collective_summary(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Collective stock across ALL outlets, plus a per-outlet total."""
    per_product = db.execute(
        select(Product.id, Product.sku, Product.name, Product.price,
               func.coalesce(func.sum(Inventory.quantity), 0).label("qty"))
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .where(Product.is_active.is_(True))
        .group_by(Product.id).order_by(Product.name)
    ).all()
    per_outlet = db.execute(
        select(Outlet.id, Outlet.name, func.coalesce(func.sum(Inventory.quantity), 0),
               func.coalesce(func.sum(Inventory.quantity * Product.price), 0))
        .outerjoin(Inventory, Inventory.outlet_id == Outlet.id)
        .outerjoin(Product, Product.id == Inventory.product_id)
        .group_by(Outlet.id).order_by(Outlet.name)
    ).all()
    return {
        "products": [{"product_id": r.id, "sku": r.sku, "product_name": r.name,
                      "total_quantity": int(r.qty), "stock_value": round(float(r.price) * int(r.qty), 2)}
                     for r in per_product],
        "outlets": [{"outlet_id": i, "outlet_name": n, "total_units": int(q), "stock_value": round(float(v), 2)}
                    for i, n, q, v in per_outlet],
    }


@router.post("/restock", response_model=InventoryRow)
def restock(data: StockChangeIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """New stock arrived at an outlet."""
    row = change_stock(db, product_id=data.product_id, outlet_id=data.outlet_id, change=data.quantity,
                       movement_type=MovementType.RESTOCK, user_id=admin.id, note=data.note)
    db.commit()
    return next(r for r in _rows(db, data.outlet_id) if r.product_id == row.product_id)


@router.post("/adjust")
def adjust(data: AdjustIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Manual correction, e.g. damaged goods (-2) or audit found extra (+1)."""
    row = change_stock(db, product_id=data.product_id, outlet_id=data.outlet_id, change=data.change,
                       movement_type=MovementType.ADJUSTMENT, user_id=admin.id, note=data.note)
    db.commit()
    return {"product_id": row.product_id, "outlet_id": row.outlet_id, "quantity": row.quantity}


@router.post("/transfer")
def transfer(data: TransferIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Move stock between outlets in ONE transaction (both succeed or both fail)."""
    src = change_stock(db, product_id=data.product_id, outlet_id=data.from_outlet_id, change=-data.quantity,
                       movement_type=MovementType.TRANSFER_OUT, user_id=admin.id, note=data.note)
    dst = change_stock(db, product_id=data.product_id, outlet_id=data.to_outlet_id, change=data.quantity,
                       movement_type=MovementType.TRANSFER_IN, user_id=admin.id, note=data.note)
    db.commit()
    return {"from_quantity": src.quantity, "to_quantity": dst.quantity}


@router.get("/movements", response_model=list[MovementOut])
def movements(product_id: int | None = None, outlet_id: int | None = None, limit: int = Query(100, le=500),
              db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = (select(StockMovement).options(selectinload(StockMovement.product), selectinload(StockMovement.outlet))
         .order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(limit))
    if product_id:
        q = q.where(StockMovement.product_id == product_id)
    if outlet_id:
        q = q.where(StockMovement.outlet_id == outlet_id)
    return db.scalars(q).all()
