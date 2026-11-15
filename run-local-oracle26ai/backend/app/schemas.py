"""Pydantic schemas: validate request bodies and shape JSON responses (the API contract)."""
import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Allowed values. They match the CHECK constraints in database/01_schema.sql.
class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    CUSTOMER = "CUSTOMER"


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"      # shipped, then sent back: stock returned, payment refunded


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"    # order cancelled (or expired) before it was paid


class DeliveryStatus(str, enum.Enum):
    NOT_SHIPPED = "NOT_SHIPPED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"


class MovementType(str, enum.Enum):
    RESTOCK = "RESTOCK"
    SALE = "SALE"
    CANCEL = "CANCEL"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    MANUAL = "MANUAL"          # someone changed INVENTORY directly in SQL Developer


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    phone: str | None = None
    address: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr
    role: Role
    phone: str | None
    address: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Catalogue ----------
class OutletIn(BaseModel):
    name: str = Field(min_length=2)
    city: str
    address: str | None = None


class OutletOut(ORM):
    id: int
    name: str
    city: str
    address: str | None


class CategoryOut(ORM):
    id: int
    name: str


class SupplierOut(ORM):
    id: int
    name: str
    contact_email: str | None
    phone: str | None


class ProductIn(BaseModel):
    sku: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    price: float = Field(ge=0)
    image_url: str | None = None
    reorder_level: int = Field(default=10, ge=0)
    category_id: int | None = None
    supplier_id: int | None = None
    is_active: bool = True


class ProductOut(ORM):
    id: int
    sku: str
    name: str
    description: str | None
    price: float
    image_url: str | None
    reorder_level: int
    is_active: bool
    category: CategoryOut | None
    supplier: SupplierOut | None
    total_stock: int = 0


# ---------- Inventory ----------
class InventoryRow(BaseModel):
    product_id: int
    sku: str
    product_name: str
    outlet_id: int
    outlet_name: str
    quantity: int
    reorder_level: int
    low_stock: bool


class StockChangeIn(BaseModel):
    product_id: int
    outlet_id: int
    quantity: int = Field(gt=0)
    note: str | None = None


class AdjustIn(BaseModel):
    product_id: int
    outlet_id: int
    change: int  # can be negative (damaged/lost) or positive (found in audit)
    note: str = Field(min_length=3)


class TransferIn(BaseModel):
    product_id: int
    from_outlet_id: int
    to_outlet_id: int
    quantity: int = Field(gt=0)
    note: str | None = None


class MovementOut(ORM):
    id: int
    product_id: int
    outlet_id: int
    change: int
    movement_type: MovementType
    note: str | None
    order_id: int | None
    created_at: datetime
    product: "ProductMini"
    outlet: OutletOut


class ProductMini(ORM):
    id: int
    sku: str
    name: str


# ---------- Orders ----------
class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100)


class OrderIn(BaseModel):
    outlet_id: int
    items: list[OrderItemIn] = Field(min_length=1)
    shipping_address: str = Field(min_length=5)


class OrderItemOut(ORM):
    product_id: int
    quantity: int
    unit_price: float
    product: ProductMini


class PaymentOut(ORM):
    amount: float
    method: str | None
    status: PaymentStatus
    transaction_ref: str | None
    updated_at: datetime


class DeliveryOut(ORM):
    status: DeliveryStatus
    tracking_number: str | None
    courier: str | None
    updated_at: datetime


class CustomerMini(ORM):
    id: int
    name: str
    email: str


class OrderOut(ORM):
    id: int
    status: OrderStatus
    total_amount: float
    shipping_address: str
    created_at: datetime
    outlet: OutletOut
    customer: CustomerMini
    items: list[OrderItemOut]
    payment: PaymentOut | None
    delivery: DeliveryOut | None


class PaymentIn(BaseModel):
    method: str = Field(pattern="^(CARD|UPI|NETBANKING)$")
    # Demo gateway: card ending 0000 or UPI id starting "fail" simulates a declined payment.
    card_number: str | None = None
    upi_id: str | None = None


class DeliveryUpdateIn(BaseModel):
    status: DeliveryStatus
    tracking_number: str | None = None
    courier: str | None = None


MovementOut.model_rebuild()
