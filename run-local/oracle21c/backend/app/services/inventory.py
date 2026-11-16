"""Business rules for stock: restock, adjust (damage / audit) and transfers between outlets.

Pattern used for every stock change (inside ONE transaction):
  1. check the request makes sense (product and outlet exist, quantity > 0, ...)
  2. lock the stock row in Oracle      -> inventory_pkg.lock_stock   (SELECT ... FOR UPDATE)
  3. decide: is there enough stock?    -> here, in Python
  4. change it                          -> inventory_pkg.apply_stock_change
                                           (the trigger TRG_INVENTORY_AUDIT logs it in STOCK_MOVEMENTS)
Because the row stays locked until COMMIT, two people can never both take the last units.
"""
import oracledb

from ..database import call_procedure, query_one, transaction
from ..errors import BusinessError, invalid, not_found


def product_and_outlet(db: oracledb.Connection, product_id: int, outlet_id: int) -> dict:
    product = query_one(db, "SELECT product_id, name, is_active, price FROM products WHERE product_id = :id",
                        {"id": product_id})
    if not product:
        raise not_found("Product")
    if not query_one(db, "SELECT 1 AS ok FROM outlets WHERE outlet_id = :id", {"id": outlet_id}):
        raise not_found("Outlet")
    return product


def lock_stock(db: oracledb.Connection, product_id: int, outlet_id: int) -> int:
    return call_procedure(db, "inventory_pkg.lock_stock", out={"p_quantity": int},
                          p_product_id=product_id, p_outlet_id=outlet_id)["p_quantity"]


def take_stock(db: oracledb.Connection, product: dict, outlet_id: int, quantity: int, movement_type: str,
               user_id: int | None, order_id: int | None = None, note: str | None = None) -> None:
    """Remove `quantity` units, refusing if the shelf doesn't have them."""
    available = lock_stock(db, product["product_id"], outlet_id)
    if available < quantity:
        raise BusinessError(409, f"Not enough stock for '{product['name']}' at this outlet (available: {available})")
    change_stock(db, product["product_id"], outlet_id, -quantity, movement_type, user_id, order_id, note)


def change_stock(db: oracledb.Connection, product_id: int, outlet_id: int, change: int, movement_type: str,
                 user_id: int | None, order_id: int | None = None, note: str | None = None) -> None:
    call_procedure(db, "inventory_pkg.apply_stock_change", p_product_id=product_id, p_outlet_id=outlet_id,
                   p_change=change, p_movement_type=movement_type, p_user_id=user_id, p_order_id=order_id,
                   p_note=note)


def restock(db: oracledb.Connection, user: dict, product_id: int, outlet_id: int, quantity: int, note: str | None) -> None:
    def work():
        product_and_outlet(db, product_id, outlet_id)
        lock_stock(db, product_id, outlet_id)
        change_stock(db, product_id, outlet_id, quantity, "RESTOCK", user["id"], None, note or "New stock received")
    transaction(db, work)


def adjust(db: oracledb.Connection, user: dict, product_id: int, outlet_id: int, change: int, note: str) -> None:
    if change == 0:
        raise invalid("Change cannot be 0")
    if len(note.strip()) < 3:
        raise invalid("A reason (note) is required for adjustments")

    def work():
        product = product_and_outlet(db, product_id, outlet_id)
        if change < 0:
            take_stock(db, product, outlet_id, -change, "ADJUSTMENT", user["id"], None, note.strip())
        else:
            lock_stock(db, product_id, outlet_id)
            change_stock(db, product_id, outlet_id, change, "ADJUSTMENT", user["id"], None, note.strip())
    transaction(db, work)


def transfer(db: oracledb.Connection, user: dict, product_id: int, from_outlet: int, to_outlet: int,
             quantity: int, note: str | None) -> None:
    if from_outlet == to_outlet:
        raise invalid("Choose two different outlets")

    def work():
        product = product_and_outlet(db, product_id, from_outlet)
        product_and_outlet(db, product_id, to_outlet)
        names = {r: query_one(db, "SELECT name FROM outlets WHERE outlet_id = :id", {"id": r})["name"]
                 for r in (from_outlet, to_outlet)}
        text = note or f"Transfer: {names[from_outlet]} -> {names[to_outlet]}"
        # Lock both rows in a fixed order (lower outlet id first) so two transfers can't deadlock.
        for outlet in sorted((from_outlet, to_outlet)):
            lock_stock(db, product_id, outlet)
        # Both steps are in ONE transaction: either both happen or neither does.
        take_stock(db, product, from_outlet, quantity, "TRANSFER_OUT", user["id"], None, text)
        change_stock(db, product_id, to_outlet, quantity, "TRANSFER_IN", user["id"], None, text)
    transaction(db, work)
