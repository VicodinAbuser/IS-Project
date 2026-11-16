"""Products, categories, suppliers and outlets."""
import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db, query, query_one
from ..listing import UPDATED_WITHIN, order_by, updated_within, where_sql
from ..schemas import CategoryOut, OutletIn, OutletOut, ProductIn, ProductOut, SupplierOut
from ..security import Perm, has, require
from ..services import catalog

router = APIRouter(prefix="/api", tags=["Catalogue"])

# Stock comes from PL/SQL functions in INVENTORY_PKG, called inside the SELECT.
PRODUCT_SELECT = """
    SELECT p.product_id AS id, p.sku, p.name, p.description, p.price, p.image_url,
           p.reorder_level, p.is_active, p.created_at, p.updated_at,
           c.category_id, c.name AS category_name,
           s.supplier_id, s.name AS supplier_name, s.contact_email AS supplier_email, s.phone AS supplier_phone,
           {stock} AS total_stock
      FROM products p
      LEFT JOIN categories c ON c.category_id = p.category_id
      LEFT JOIN suppliers  s ON s.supplier_id = p.supplier_id"""
TOTAL_STOCK = "inventory_pkg.total_stock(p.product_id)"
OUTLET_STOCK = "inventory_pkg.stock_at(p.product_id, :outlet_id)"
PRODUCT_SORTS = {"name_asc": "p.name", "price_asc": "p.price", "price_desc": "p.price DESC",
                 "newest": "p.created_at DESC", "updated_desc": "p.updated_at DESC"}


def to_product(r: dict) -> ProductOut:
    return ProductOut(
        **{k: r[k] for k in ("id", "sku", "name", "description", "price", "image_url", "reorder_level", "total_stock",
                             "created_at", "updated_at")},
        is_active=bool(r["is_active"]),
        category={"id": r["category_id"], "name": r["category_name"]} if r["category_id"] else None,
        supplier={"id": r["supplier_id"], "name": r["supplier_name"], "contact_email": r["supplier_email"],
                  "phone": r["supplier_phone"]} if r["supplier_id"] else None,
    )


def fetch_product(db: oracledb.Connection, product_id: int) -> ProductOut:
    row = query_one(db, PRODUCT_SELECT.format(stock=TOTAL_STOCK) + " WHERE p.product_id = :id", {"id": product_id})
    if not row:
        raise HTTPException(404, "Product not found")
    return to_product(row)


@router.get("/products", response_model=list[ProductOut])
def list_products(search: str | None = Query(None, max_length=100), category_id: int | None = None,
                  outlet_id: int | None = Query(None, description="Show stock for one outlet only"),
                  include_inactive: bool = False, sort: str | None = None,
                  updated_within_days: int | None = UPDATED_WITHIN,
                  db: oracledb.Connection = Depends(get_db), user: dict = Depends(require(Perm.CATALOG_READ))):
    where, params = [], {}
    if not (include_inactive and has(user, Perm.CATALOG_WRITE)):      # hidden products: staff only
        where.append("p.is_active = 1")
    if search:
        where.append("(UPPER(p.name) LIKE UPPER(:search) OR UPPER(p.sku) LIKE UPPER(:search))")
        params["search"] = f"%{search.strip()}%"
    if category_id:
        where.append("p.category_id = :category_id")
        params["category_id"] = category_id
    updated_within("p.updated_at", updated_within_days, where, params)
    stock = TOTAL_STOCK
    if outlet_id:
        stock = OUTLET_STOCK
        params["outlet_id"] = outlet_id
    sql = PRODUCT_SELECT.format(stock=stock) + where_sql(where) + order_by(sort, PRODUCT_SORTS, "name_asc", "p.product_id")
    return [to_product(r) for r in query(db, sql, params)]


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: oracledb.Connection = Depends(get_db),
                _: dict = Depends(require(Perm.CATALOG_READ))):
    return fetch_product(db, product_id)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, db: oracledb.Connection = Depends(get_db),
                   _: dict = Depends(require(Perm.CATALOG_WRITE))):
    return fetch_product(db, catalog.save_product(db, None, data))


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductIn, db: oracledb.Connection = Depends(get_db),
                   _: dict = Depends(require(Perm.CATALOG_WRITE))):
    return fetch_product(db, catalog.save_product(db, product_id, data))


@router.delete("/products/{product_id}", status_code=204)
def deactivate_product(product_id: int, db: oracledb.Connection = Depends(get_db),
                       _: dict = Depends(require(Perm.CATALOG_WRITE))):
    """Soft delete: hides the product from the shop but keeps order history intact."""
    catalog.hide_product(db, product_id)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: oracledb.Connection = Depends(get_db)):
    return query(db, "SELECT category_id AS id, name FROM categories ORDER BY name")


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: oracledb.Connection = Depends(get_db), _: dict = Depends(require(Perm.CATALOG_WRITE))):
    return query(db, "SELECT supplier_id AS id, name, contact_email, phone FROM suppliers ORDER BY name")


@router.get("/outlets", response_model=list[OutletOut])
def list_outlets(db: oracledb.Connection = Depends(get_db)):
    """Public: the sign-up page lists outlets so customers can pick their nearest one."""
    return query(db, "SELECT outlet_id AS id, name, city, address FROM outlets ORDER BY name")


@router.post("/outlets", response_model=OutletOut, status_code=201)
def create_outlet(data: OutletIn, db: oracledb.Connection = Depends(get_db),
                  _: dict = Depends(require(Perm.CATALOG_WRITE))):
    new_id = catalog.create_outlet(db, data)
    return query_one(db, "SELECT outlet_id AS id, name, city, address FROM outlets WHERE outlet_id = :id", {"id": new_id})
