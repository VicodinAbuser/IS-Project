"""Stock management (staff). Reads use views; changes go through app/services/inventory.py."""
import oracledb
from fastapi import APIRouter, Depends, Query

from ..database import get_db, query, query_one
from ..listing import UPDATED_WITHIN, order_by, updated_within, where_sql
from ..schemas import AdjustIn, InventoryRow, MovementOut, MovementType, StockChangeIn, TransferIn
from ..security import Perm, require
from ..services import inventory

router = APIRouter(prefix="/api/inventory", tags=["Inventory (staff)"])

STATUS_SELECT = """SELECT product_id, sku, product_name, outlet_id, outlet_name, quantity, reorder_level, low_stock,
                          updated_at
                     FROM v_inventory_status"""
STOCK_SORTS = {"updated_desc": "updated_at DESC", "updated_asc": "updated_at", "quantity_asc": "quantity",
               "quantity_desc": "quantity DESC", "product_asc": "product_name, outlet_name",
               "outlet_asc": "outlet_name, product_name"}
MOVEMENT_SORTS = {"newest": "m.created_at DESC", "oldest": "m.created_at", "change_desc": "ABS(m.qty_change) DESC"}


def to_row(r: dict) -> InventoryRow:
    return InventoryRow(**{**r, "low_stock": bool(r["low_stock"])})


def _one(db: oracledb.Connection, product_id: int, outlet_id: int) -> InventoryRow:
    return to_row(query_one(db, STATUS_SELECT + " WHERE product_id = :p AND outlet_id = :o",
                            {"p": product_id, "o": outlet_id}))


@router.get("", response_model=list[InventoryRow])
def stock_by_outlet(outlet_id: int | None = Query(None, description="Omit for all outlets"),
                    low_only: bool = False, search: str | None = Query(None, max_length=100),
                    sort: str | None = None, updated_within_days: int | None = UPDATED_WITHIN,
                    db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.STOCK_READ))):
    where, params = [], {}
    if outlet_id:
        where.append("outlet_id = :outlet_id")
        params["outlet_id"] = outlet_id
    if low_only:
        where.append("low_stock = 1")
    if search:
        where.append("(UPPER(product_name) LIKE UPPER(:q) OR UPPER(sku) LIKE UPPER(:q))")
        params["q"] = f"%{search.strip()}%"
    updated_within("updated_at", updated_within_days, where, params)
    sql = STATUS_SELECT + where_sql(where) + order_by(sort, STOCK_SORTS, "outlet_asc", "product_id")
    return [to_row(r) for r in query(db, sql, params)]


@router.get("/low-stock", response_model=list[InventoryRow])
def low_stock(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.STOCK_READ))):
    return [to_row(r) for r in query(db, STATUS_SELECT + " WHERE low_stock = 1 ORDER BY quantity, product_name")]


@router.get("/summary")
def collective_summary(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.STOCK_READ))):
    """Collective stock across ALL outlets, plus a per-outlet total."""
    products = query(db, """
        SELECT product_id, sku, product_name, total_stock AS total_quantity, stock_value
          FROM v_product_stock WHERE is_active = 1 ORDER BY product_name""")
    outlets = query(db, """
        SELECT o.outlet_id, o.name AS outlet_name,
               NVL(SUM(v.quantity), 0) AS total_units, NVL(SUM(v.stock_value), 0) AS stock_value
          FROM outlets o
          LEFT JOIN v_inventory_status v ON v.outlet_id = o.outlet_id
         GROUP BY o.outlet_id, o.name
         ORDER BY o.name""")
    return {"products": products, "outlets": outlets}


@router.post("/restock", response_model=InventoryRow)
def restock(data: StockChangeIn, db: oracledb.Connection = Depends(get_db),
            user: dict = Depends(require(Perm.STOCK_WRITE))):
    """New stock arrived at an outlet."""
    inventory.restock(db, user, data.product_id, data.outlet_id, data.quantity, data.note)
    return _one(db, data.product_id, data.outlet_id)


@router.post("/adjust", response_model=InventoryRow)
def adjust(data: AdjustIn, db: oracledb.Connection = Depends(get_db), user: dict = Depends(require(Perm.STOCK_WRITE))):
    """Manual correction, e.g. damaged goods (-2) or audit found extra (+1)."""
    inventory.adjust(db, user, data.product_id, data.outlet_id, data.change, data.note)
    return _one(db, data.product_id, data.outlet_id)


@router.post("/transfer")
def transfer(data: TransferIn, db: oracledb.Connection = Depends(get_db), user: dict = Depends(require(Perm.STOCK_WRITE))):
    """Move stock between outlets in ONE transaction (both succeed or both fail)."""
    inventory.transfer(db, user, data.product_id, data.from_outlet_id, data.to_outlet_id, data.quantity, data.note)
    return query_one(db, """SELECT inventory_pkg.stock_at(:p, :f) AS from_quantity,
                                   inventory_pkg.stock_at(:p, :t) AS to_quantity FROM dual""",
                     {"p": data.product_id, "f": data.from_outlet_id, "t": data.to_outlet_id})


@router.get("/movements", response_model=list[MovementOut])
def movements(product_id: int | None = None, outlet_id: int | None = None, movement_type: MovementType | None = None,
              search: str | None = Query(None, max_length=100), sort: str | None = None,
              updated_within_days: int | None = UPDATED_WITHIN, limit: int = Query(100, ge=1, le=1000),
              db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.STOCK_READ))):
    """The audit log written by trigger TRG_INVENTORY_AUDIT."""
    where, params = [], {}
    if product_id:
        where.append("m.product_id = :product_id")
        params["product_id"] = product_id
    if outlet_id:
        where.append("m.outlet_id = :outlet_id")
        params["outlet_id"] = outlet_id
    if movement_type:
        where.append("m.movement_type = :mtype")
        params["mtype"] = movement_type.value
    if search:
        where.append("(UPPER(p.name) LIKE UPPER(:q) OR UPPER(p.sku) LIKE UPPER(:q) OR UPPER(m.note) LIKE UPPER(:q))")
        params["q"] = f"%{search.strip()}%"
    updated_within("m.created_at", updated_within_days, where, params)
    rows = query(db, f"""
        SELECT m.movement_id, m.product_id, m.outlet_id, m.qty_change, m.movement_type, m.note, m.order_id,
               m.created_at, p.sku, p.name AS product_name, o.name AS outlet_name, o.city, o.address,
               u.full_name AS changed_by
          FROM stock_movements m
          JOIN products p ON p.product_id = m.product_id
          JOIN outlets  o ON o.outlet_id  = m.outlet_id
          LEFT JOIN users u ON u.user_id = m.user_id
         {where_sql(where)}
         {order_by(sort, MOVEMENT_SORTS, "newest", "m.movement_id DESC")}
         FETCH FIRST {limit} ROWS ONLY""", params)
    return [MovementOut(id=r["movement_id"], product_id=r["product_id"], outlet_id=r["outlet_id"],
                        change=r["qty_change"], movement_type=r["movement_type"], note=r["note"],
                        order_id=r["order_id"], created_at=r["created_at"], changed_by=r["changed_by"],
                        product={"id": r["product_id"], "sku": r["sku"], "name": r["product_name"]},
                        outlet={"id": r["outlet_id"], "name": r["outlet_name"], "city": r["city"],
                                "address": r["address"]})
            for r in rows]
