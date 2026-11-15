"""Products, categories, suppliers and outlets."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Category, Inventory, Outlet, Product, Supplier, User
from ..schemas import CategoryOut, OutletIn, OutletOut, ProductIn, ProductOut, SupplierOut
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["Catalogue"])


def _stock_map(db: Session, product_ids: list[int], outlet_id: int | None = None) -> dict[int, int]:
    q = select(Inventory.product_id, func.coalesce(func.sum(Inventory.quantity), 0)) \
        .where(Inventory.product_id.in_(product_ids)).group_by(Inventory.product_id)
    if outlet_id:
        q = q.where(Inventory.outlet_id == outlet_id)
    return dict(db.execute(q).all())


def _with_stock(db: Session, products: list[Product], outlet_id: int | None = None) -> list[ProductOut]:
    stock = _stock_map(db, [p.id for p in products], outlet_id)
    return [ProductOut.model_validate(p).model_copy(update={"total_stock": stock.get(p.id, 0)})
            for p in products]


@router.get("/products", response_model=list[ProductOut])
def list_products(search: str | None = None, category_id: int | None = None,
                  outlet_id: int | None = Query(None, description="Show stock for one outlet only"),
                  include_inactive: bool = False,
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = select(Product).options(selectinload(Product.category), selectinload(Product.supplier)) \
        .order_by(Product.name)
    if not include_inactive:
        q = q.where(Product.is_active.is_(True))
    if search:
        like = f"%{search}%"
        q = q.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if category_id:
        q = q.where(Product.category_id == category_id)
    return _with_stock(db, list(db.scalars(q)), outlet_id)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return _with_stock(db, [p])[0]


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = Product(**data.model_dump())
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "SKU already exists or invalid category/supplier")
    db.refresh(p)
    return _with_stock(db, [p])[0]


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductIn, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "SKU already exists or invalid category/supplier")
    db.refresh(p)
    return _with_stock(db, [p])[0]


@router.delete("/products/{product_id}", status_code=204)
def deactivate_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Soft delete: hides the product from the shop but keeps order history intact."""
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    p.is_active = False
    db.commit()


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.name)).all()


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.scalars(select(Supplier).order_by(Supplier.name)).all()


@router.get("/outlets", response_model=list[OutletOut])
def list_outlets(db: Session = Depends(get_db)):
    return db.scalars(select(Outlet).order_by(Outlet.name)).all()


@router.post("/outlets", response_model=OutletOut, status_code=201)
def create_outlet(data: OutletIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    o = Outlet(**data.model_dump())
    db.add(o)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Outlet name already exists")
    return o
