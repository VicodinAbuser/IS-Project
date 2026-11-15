// TypeScript interfaces mirroring the backend's JSON (Pydantic schemas).
export type Role = 'ADMIN' | 'CUSTOMER';
export type OrderStatus = 'PENDING_PAYMENT' | 'PAID' | 'CANCELLED' | 'RETURNED';
export type PaymentStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'REFUNDED' | 'CANCELLED';
export type DeliveryStatus = 'NOT_SHIPPED' | 'PACKED' | 'SHIPPED' | 'OUT_FOR_DELIVERY' | 'DELIVERED' | 'RETURNED';

export interface User { id: number; name: string; email: string; role: Role; phone?: string; address?: string; }
export interface AuthResponse { access_token: string; token_type: string; user: User; }

export interface Outlet { id: number; name: string; city: string; address?: string; }
export interface Category { id: number; name: string; }
export interface Supplier { id: number; name: string; contact_email?: string; phone?: string; }

export interface Product {
  id: number; sku: string; name: string; description?: string; price: number; image_url?: string;
  reorder_level: number; is_active: boolean; category?: Category; supplier?: Supplier; total_stock: number;
}
export interface ProductInput {
  sku: string; name: string; description?: string; price: number; image_url?: string;
  reorder_level: number; category_id?: number | null; supplier_id?: number | null; is_active: boolean;
}

export interface InventoryRow {
  product_id: number; sku: string; product_name: string; outlet_id: number; outlet_name: string;
  quantity: number; reorder_level: number; low_stock: boolean;
}
export interface StockMovement {
  id: number; change: number; movement_type: string; note?: string; order_id?: number; created_at: string;
  product: { id: number; sku: string; name: string }; outlet: Outlet;
}

export interface OrderItem { product_id: number; quantity: number; unit_price: number; product: { id: number; sku: string; name: string }; }
export interface Order {
  id: number; status: OrderStatus; total_amount: number; shipping_address: string; created_at: string;
  outlet: Outlet; customer: { id: number; name: string; email: string }; items: OrderItem[];
  payment?: { amount: number; method?: string; status: PaymentStatus; transaction_ref?: string };
  delivery?: { status: DeliveryStatus; tracking_number?: string; courier?: string; updated_at: string };
}

export interface Dashboard {
  total_revenue: number; paid_orders: number; pending_payment: number; to_ship: number; products: number;
  outlets: number; total_units_in_stock: number; low_stock_items: number;
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
