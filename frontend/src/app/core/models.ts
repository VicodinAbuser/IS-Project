// TypeScript interfaces mirroring the backend's JSON (Pydantic schemas in backend/app/schemas.py).
export type Role = 'ADMIN' | 'STAFF' | 'CUSTOMER';
export type ProfileCode = 'ADMIN' | 'STORE_MANAGER' | 'WAREHOUSE_STAFF' | 'CUSTOMER';
export type Permission =
  | 'CATALOG_READ' | 'CATALOG_WRITE' | 'ORDER_PLACE' | 'ORDER_READ_OWN' | 'ORDER_READ_ALL' | 'ORDER_MANAGE'
  | 'STOCK_READ' | 'STOCK_WRITE' | 'REPORT_VIEW' | 'REPORT_DOWNLOAD' | 'USER_READ' | 'USER_MANAGE';
export type OrderStatus = 'PENDING_PAYMENT' | 'PAID' | 'CANCELLED' | 'RETURNED';
export type PaymentStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'REFUNDED' | 'CANCELLED';
export type DeliveryStatus = 'NOT_SHIPPED' | 'PACKED' | 'SHIPPED' | 'OUT_FOR_DELIVERY' | 'DELIVERED' | 'RETURNED';

export interface AddressFields {
  phone?: string | null; address_line?: string | null; city?: string | null; state?: string | null;
  pincode?: string | null; preferred_outlet_id?: number | null;
}
export interface User extends AddressFields {
  id: number; name: string; email: string; role: Role; is_staff: boolean;
  profiles: ProfileCode[]; permissions: Permission[];
}
/** The session itself is an HttpOnly cookie: the page never sees a token. */
export interface LoginResponse { user: User; session_expires_in_minutes: number; }

export interface UserRow {
  id: number; name: string; email: string; account_status: 'ACTIVE' | 'DISABLED'; profiles: ProfileCode[];
  is_staff: boolean; phone?: string; city?: string; created_at: string; updated_at: string;
  last_login_at?: string; locked_until?: string; orders: number; total_spent: number;
}
export interface UserDetail extends UserRow {
  permissions: Permission[]; address_line?: string; state?: string; pincode?: string; preferred_outlet?: string;
  failed_login_count: number;
}
export interface ProfileInfo {
  code: ProfileCode; name: string; description?: string; is_staff: boolean; users: number; permissions: Permission[];
}
export interface PermissionInfo { code: Permission; name: string; module: string; access_type: string; description?: string; }

export interface Outlet { id: number; name: string; city: string; address?: string; }
export interface Category { id: number; name: string; }
export interface Supplier { id: number; name: string; contact_email?: string; phone?: string; }

export interface Product {
  id: number; sku: string; name: string; description?: string; price: number; image_url?: string;
  reorder_level: number; is_active: boolean; category?: Category; supplier?: Supplier; total_stock: number;
  created_at?: string; updated_at?: string;
}
export interface ProductInput {
  sku: string; name: string; description?: string; price: number; image_url?: string;
  reorder_level: number; category_id?: number | null; supplier_id?: number | null; is_active: boolean;
}

export interface InventoryRow {
  product_id: number; sku: string; product_name: string; outlet_id: number; outlet_name: string;
  quantity: number; reorder_level: number; low_stock: boolean; updated_at: string;
}
export interface StockMovement {
  id: number; change: number; movement_type: string; note?: string; order_id?: number; created_at: string;
  changed_by?: string; product: { id: number; sku: string; name: string }; outlet: Outlet;
}

export interface OrderItem { product_id: number; quantity: number; unit_price: number; product: { id: number; sku: string; name: string }; }
export interface Order {
  id: number; status: OrderStatus; total_amount: number; shipping_address: string; created_at: string; updated_at: string;
  outlet: Outlet; customer: { id: number; name: string; email: string; phone?: string }; items: OrderItem[];
  payment?: { amount: number; method?: string; status: PaymentStatus; transaction_ref?: string; updated_at: string };
  delivery?: { status: DeliveryStatus; tracking_number?: string; courier?: string; updated_at: string };
}

export interface Dashboard {
  total_revenue: number; paid_orders: number; pending_payment: number; to_ship: number; products: number;
  outlets: number; total_units_in_stock: number; low_stock_items: number; oracle_version: string;
}
export interface QuarterlyReport {
  year: number; quarter: number; period: string;
  summary: { orders: number; units_sold: number; revenue: number };
  by_outlet: { outlet: string; orders: number; units: number; revenue: number }[];
  by_product: { sku: string; product: string; units: number; revenue: number }[];
  by_category: { category: string; units: number; revenue: number }[];
  monthly: { month: string; revenue: number }[];
  current_stock_by_outlet: { outlet: string; units: number }[];
}
export interface CartItem { product: Product; quantity: number; }

/** Choices for the "Sort by" and "Updated" drop-downs. The values are the API's ?sort= names. */
export interface Choice<T = string> { value: T; label: string; }
export const UPDATED_WITHIN: Choice<number | null>[] = [
  { value: null, label: 'Any time' }, { value: 1, label: 'Today' },
  { value: 7, label: 'Last 7 days' }, { value: 30, label: 'Last 30 days' }, { value: 90, label: 'Last 90 days' },
];
