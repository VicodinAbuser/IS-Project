"""Pydantic schemas: validate request bodies and shape JSON responses (the API contract)."""
import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# Allowed values. They match the CHECK constraints in database/01_schema.sql.
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


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class ProfileCode(str, enum.Enum):
    ADMIN = "ADMIN"
    STORE_MANAGER = "STORE_MANAGER"
    WAREHOUSE_STAFF = "WAREHOUSE_STAFF"
    CUSTOMER = "CUSTOMER"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _blank_to_none(v):
    return (v.strip() or None) if isinstance(v, str) else v


# ---------- Auth and the logged-in user ----------
class AddressFields(BaseModel):
    phone: str | None = Field(None, pattern=r"^[0-9+\- ]{8,20}$")
    address_line: str | None = Field(None, max_length=300)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    pincode: str | None = Field(None, pattern=r"^[0-9]{6}$")
    preferred_outlet_id: int | None = None

    _clean = field_validator("phone", "address_line", "city", "state", "pincode", mode="before")(_blank_to_none)


class RegisterIn(AddressFields):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class MyProfileIn(AddressFields):
    name: str = Field(min_length=2, max_length=100)


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr
    role: str                  # ADMIN, STAFF or CUSTOMER: a summary of the profiles for the UI
    is_staff: bool
    profiles: list[str]
    permissions: list[str]
    phone: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    preferred_outlet_id: int | None = None


class LoginOut(BaseModel):
    """The session itself is in the HttpOnly cookie; the body only describes the user."""
    user: UserOut
    session_expires_in_minutes: int


# ---------- Users and access (admin) ----------
class UserRow(BaseModel):
    id: int
    name: str
    email: str
    account_status: AccountStatus
    profiles: list[str]
    is_staff: bool
    phone: str | None
    city: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    locked_until: datetime | None
    orders: int
    total_spent: float


class UserDetail(UserRow):
    permissions: list[str]
    address_line: str | None
    state: str | None
    pincode: str | None
    preferred_outlet: str | None
    failed_login_count: int


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    profiles: list[ProfileCode] = Field(min_length=1)


class ProfilesIn(BaseModel):
    profiles: list[ProfileCode] = Field(min_length=1)


class StatusIn(BaseModel):
    status: AccountStatus


class PermissionOut(BaseModel):
    code: str
    name: str
    module: str
    access_type: str
    description: str | None


class ProfileOut(BaseModel):
    code: str
    name: str
    description: str | None
    is_staff: bool
    users: int
    permissions: list[str]


# ---------- Catalogue ----------
class OutletIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    address: str | None = Field(None, max_length=500)


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
    description: str | None = Field(None, max_length=1000)
    price: float = Field(ge=0, le=10_000_000)
    image_url: str | None = Field(None, max_length=500, pattern=r"^(https://\S+)?$")
    reorder_level: int = Field(default=10, ge=0, le=100_000)
    category_id: int | None = None
    supplier_id: int | None = None
    is_active: bool = True

    _clean = field_validator("description", "image_url", mode="before")(_blank_to_none)


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
    created_at: datetime
    updated_at: datetime


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
    updated_at: datetime


class StockChangeIn(BaseModel):
    product_id: int
    outlet_id: int
    quantity: int = Field(gt=0, le=100_000)
    note: str | None = Field(None, max_length=200)


class AdjustIn(BaseModel):
    product_id: int
    outlet_id: int
    change: int = Field(ge=-100_000, le=100_000)  # negative (damaged/lost) or positive (found in audit)
    note: str = Field(min_length=3, max_length=200)


class TransferIn(BaseModel):
    product_id: int
    from_outlet_id: int
    to_outlet_id: int
    quantity: int = Field(gt=0, le=100_000)
    note: str | None = Field(None, max_length=200)


class ProductMini(ORM):
    id: int
    sku: str
    name: str


class MovementOut(ORM):
    id: int
    product_id: int
    outlet_id: int
    change: int
    movement_type: MovementType
    note: str | None
    order_id: int | None
    created_at: datetime
    changed_by: str | None
    product: ProductMini
    outlet: OutletOut


# ---------- Orders ----------
class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100)


class OrderIn(BaseModel):
    outlet_id: int
    items: list[OrderItemIn] = Field(min_length=1)
    shipping_address: str = Field(min_length=5, max_length=500)


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
    phone: str | None = None


class OrderOut(ORM):
    id: int
    status: OrderStatus
    total_amount: float
    shipping_address: str
    created_at: datetime
    updated_at: datetime
    outlet: OutletOut
    customer: CustomerMini
    items: list[OrderItemOut]
    payment: PaymentOut | None
    delivery: DeliveryOut | None


class PaymentIn(BaseModel):
    method: str = Field(pattern="^(CARD|UPI|NETBANKING)$")
    # Demo gateway: card ending 0000 or UPI id starting "fail" simulates a declined payment.
    card_number: str | None = Field(None, max_length=25)
    upi_id: str | None = Field(None, max_length=60)


class DeliveryUpdateIn(BaseModel):
    status: DeliveryStatus
    tracking_number: str | None = Field(None, max_length=100)
    courier: str | None = Field(None, max_length=100)
