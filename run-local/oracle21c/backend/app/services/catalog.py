"""Business rules for the catalogue: products and outlets."""
import oracledb

from ..database import call_procedure, query_one, transaction
from ..errors import conflict, not_found
from ..schemas import OutletIn, ProductIn


def _check_references(db: oracledb.Connection, data: ProductIn) -> None:
    if data.category_id and not query_one(db, "SELECT 1 AS ok FROM categories WHERE category_id = :id",
                                          {"id": data.category_id}):
        raise not_found("Category")
    if data.supplier_id and not query_one(db, "SELECT 1 AS ok FROM suppliers WHERE supplier_id = :id",
                                          {"id": data.supplier_id}):
        raise not_found("Supplier")


def save_product(db: oracledb.Connection, product_id: int | None, data: ProductIn) -> int:
    """Create (product_id None) or update a product. SKUs are stored in capitals and must be unique."""
    sku = data.sku.strip().upper()

    def work():
        _check_references(db, data)
        clash = query_one(db, "SELECT product_id FROM products WHERE sku = :sku", {"sku": sku})
        if clash and clash["product_id"] != product_id:
            raise conflict("A product with this SKU already exists")
        if product_id is not None and not query_one(db, "SELECT 1 AS ok FROM products WHERE product_id = :id FOR UPDATE",
                                                    {"id": product_id}):
            raise not_found("Product")
        return call_procedure(db, "inventory_pkg.save_product", out={"p_product_id": int}, p_product_id=product_id,
                              p_sku=sku, p_name=data.name.strip(), p_description=data.description,
                              p_price=round(data.price, 2), p_image_url=data.image_url,
                              p_reorder_level=data.reorder_level, p_is_active=1 if data.is_active else 0,
                              p_category_id=data.category_id, p_supplier_id=data.supplier_id)["p_product_id"]
    return transaction(db, work)


def hide_product(db: oracledb.Connection, product_id: int) -> None:
    """Soft delete: the product disappears from the shop but old orders keep it."""
    transaction(db, lambda: call_procedure(db, "inventory_pkg.set_product_active", p_product_id=product_id,
                                           p_is_active=0))


def create_outlet(db: oracledb.Connection, data: OutletIn) -> int:
    def work():
        if query_one(db, "SELECT 1 AS ok FROM outlets WHERE UPPER(name) = UPPER(:n)", {"n": data.name.strip()}):
            raise conflict("An outlet with this name already exists")
        return call_procedure(db, "inventory_pkg.create_outlet", out={"p_outlet_id": int}, p_name=data.name.strip(),
                              p_city=data.city.strip(), p_address=data.address)["p_outlet_id"]
    return transaction(db, work)
