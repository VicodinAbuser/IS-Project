"""Admin-only stock management. Every change calls a procedure in INVENTORY_PKG."""
import oracledb
from fastapi import APIRouter, Depends, Query

from ..database import call_procedure, get_db, query, query_one
from ..schemas import AdjustIn, InventoryRow, MovementOut, StockChangeIn, TransferIn
from ..security import require_admin

router = APIRouter(prefix="/api/inventory", tags=["Inventory (admin)"])

STATUS_SELECT = """SELECT product_id, sku, product_name, outlet_id, outlet_name, quantity, reorder_level, low_stock
                     FROM v_inventory_status"""


def to_row(r: dict) -> InventoryRow:
    return InventoryRow(**{**r, "low_stock": bool(r["low_stock"])})


@router.get("", response_model=list[InventoryRow])
def stock_by_outlet(outlet_id: int | None = Query(None, description="Omit for all outlets"),
                    db: oracledb.Connection = Depends(get_db), _: dict = Depends(require_admin)):
    sql, params = STATUS_SELECT, {}
    if outlet_id:
        sql += " WHERE outlet_id = :outlet_id"
        params["outlet_id"] = outlet_id
    return [to_row(r) for r in query(db, sql + " ORDER BY outlet_name, product_name", params)]


@router.get("/low-stock", response_model=list[InventoryRow])
def low_stock(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require_admin)):
    return [to_row(r) for r in query(db, STATUS_SELECT + " WHERE low_stock = 1 ORDER BY quantity, product_name")]


@router.get("/summary")
def collective_summary(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require_admin)):
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
def restock(data: StockChangeIn, db: oracledb.Connection = Depends(get_db), admin: dict = Depends(require_admin)):
    """New stock arrived at an outlet."""
    call_procedure(db, "inventory_pkg.restock", p_product_id=data.product_id, p_outlet_id=data.outlet_id,
                   p_quantity=data.quantity, p_note=data.note, p_user_id=admin["id"])
    return to_row(query_one(db, STATUS_SELECT + " WHERE product_id = :p AND outlet_id = :o",
                            {"p": data.product_id, "o": data.outlet_id}))


@router.post("/adjust")
def adjust(data: AdjustIn, db: oracledb.Connection = Depends(get_db), admin: dict = Depends(require_admin)):
    """Manual correction, e.g. damaged goods (-2) or audit found extra (+1)."""
    call_procedure(db, "inventory_pkg.adjust_stock", p_product_id=data.product_id, p_outlet_id=data.outlet_id,
                   p_change=data.change, p_note=data.note, p_user_id=admin["id"])
    return query_one(db, "SELECT product_id, outlet_id, quantity FROM inventory WHERE product_id = :p AND outlet_id = :o",
                     {"p": data.product_id, "o": data.outlet_id})


@router.post("/transfer")
def transfer(data: TransferIn, db: oracledb.Connection = Depends(get_db), admin: dict = Depends(require_admin)):
    """Move stock between outlets in ONE transaction (both succeed or both fail)."""
    call_procedure(db, "inventory_pkg.transfer_stock", p_product_id=data.product_id,
                   p_from_outlet_id=data.from_outlet_id, p_to_outlet_id=data.to_outlet_id,
                   p_quantity=data.quantity, p_note=data.note, p_user_id=admin["id"])
    return query_one(db, """SELECT inventory_pkg.stock_at(:p, :f) AS from_quantity,
                                   inventory_pkg.stock_at(:p, :t) AS to_quantity FROM dual""",
                     {"p": data.product_id, "f": data.from_outlet_id, "t": data.to_outlet_id})


@router.get("/movements", response_model=list[MovementOut])
def movements(product_id: int | None = None, outlet_id: int | None = None, limit: int = Query(100, le=500),
              db: oracledb.Connection = Depends(get_db), _: dict = Depends(require_admin)):
    """The audit log written by trigger TRG_INVENTORY_AUDIT."""
    where, params = [], {"lim": limit}
    if product_id:
        where.append("m.product_id = :product_id")
        params["product_id"] = product_id
    if outlet_id:
        where.append("m.outlet_id = :outlet_id")
        params["outlet_id"] = outlet_id
    rows = query(db, f"""
        SELECT m.movement_id, m.product_id, m.outlet_id, m.qty_change, m.movement_type, m.note, m.order_id,
               m.created_at, p.sku, p.name AS product_name, o.name AS outlet_name, o.city, o.address
          FROM stock_movements m
          JOIN products p ON p.product_id = m.product_id
          JOIN outlets  o ON o.outlet_id  = m.outlet_id
         {"WHERE " + " AND ".join(where) if where else ""}
         ORDER BY m.created_at DESC, m.movement_id DESC
         FETCH FIRST :lim ROWS ONLY""", params)
    return [MovementOut(id=r["movement_id"], product_id=r["product_id"], outlet_id=r["outlet_id"],
                        change=r["qty_change"], movement_type=r["movement_type"], note=r["note"],
                        order_id=r["order_id"], created_at=r["created_at"],
                        product={"id": r["product_id"], "sku": r["sku"], "name": r["product_name"]},
                        outlet={"id": r["outlet_id"], "name": r["outlet_name"], "city": r["city"],
                                "address": r["address"]})
            for r in rows]
