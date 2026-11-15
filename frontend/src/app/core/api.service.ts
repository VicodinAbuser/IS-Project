import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  Category, Dashboard, DeliveryStatus, InventoryRow, Order, Outlet, Product, ProductInput,
  QuarterlyReport, StockMovement, Supplier,
} from './models';

/** Every call from the UI to the backend REST API goes through this service. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiUrl;

  private params(obj: Record<string, unknown>): HttpParams {
    let p = new HttpParams();
    for (const [k, v] of Object.entries(obj)) if (v !== null && v !== undefined && v !== '') p = p.set(k, String(v));
    return p;
  }

  // Catalogue
  getProducts(filter: { search?: string; category_id?: number; outlet_id?: number; include_inactive?: boolean } = {}) {
    return this.http.get<Product[]>(`${this.base}/products`, { params: this.params(filter) });
  }
  createProduct(p: ProductInput) { return this.http.post<Product>(`${this.base}/products`, p); }
  updateProduct(id: number, p: ProductInput) { return this.http.put<Product>(`${this.base}/products/${id}`, p); }
  deactivateProduct(id: number) { return this.http.delete<void>(`${this.base}/products/${id}`); }
  getCategories() { return this.http.get<Category[]>(`${this.base}/categories`); }
  getSuppliers() { return this.http.get<Supplier[]>(`${this.base}/suppliers`); }
  getOutlets() { return this.http.get<Outlet[]>(`${this.base}/outlets`); }
  createOutlet(o: { name: string; city: string; address?: string }) { return this.http.post<Outlet>(`${this.base}/outlets`, o); }

  // Inventory (admin)
  getInventory(outletId?: number) { return this.http.get<InventoryRow[]>(`${this.base}/inventory`, { params: this.params({ outlet_id: outletId }) }); }
  getLowStock() { return this.http.get<InventoryRow[]>(`${this.base}/inventory/low-stock`); }
  getInventorySummary() { return this.http.get<any>(`${this.base}/inventory/summary`); }
  restock(body: { product_id: number; outlet_id: number; quantity: number; note?: string }) {
    return this.http.post<InventoryRow>(`${this.base}/inventory/restock`, body);
  }
  adjust(body: { product_id: number; outlet_id: number; change: number; note: string }) {
    return this.http.post(`${this.base}/inventory/adjust`, body);
  }
  transfer(body: { product_id: number; from_outlet_id: number; to_outlet_id: number; quantity: number; note?: string }) {
    return this.http.post(`${this.base}/inventory/transfer`, body);
  }
  getMovements(limit = 100) { return this.http.get<StockMovement[]>(`${this.base}/inventory/movements`, { params: this.params({ limit }) }); }

  // Orders, payment, delivery
  placeOrder(body: { outlet_id: number; shipping_address: string; items: { product_id: number; quantity: number }[] }) {
    return this.http.post<Order>(`${this.base}/orders`, body);
  }
  myOrders() { return this.http.get<Order[]>(`${this.base}/orders/my`); }
  getOrder(id: number) { return this.http.get<Order>(`${this.base}/orders/${id}`); }
  allOrders(filter: { status?: string; outlet_id?: number; delivery_status?: string } = {}) {
    return this.http.get<Order[]>(`${this.base}/orders`, { params: this.params(filter) });
  }
  pay(id: number, body: { method: string; card_number?: string; upi_id?: string }) {
    return this.http.post<Order>(`${this.base}/orders/${id}/pay`, body);
  }
  cancelOrder(id: number) { return this.http.post<Order>(`${this.base}/orders/${id}/cancel`, {}); }
  updateDelivery(id: number, body: { status: DeliveryStatus; courier?: string; tracking_number?: string }) {
    return this.http.patch<Order>(`${this.base}/orders/${id}/delivery`, body);
  }

  // Reports (admin)
  getDashboard() { return this.http.get<Dashboard>(`${this.base}/reports/dashboard`); }
  getQuarterly(year: number, quarter: number) {
    return this.http.get<QuarterlyReport>(`${this.base}/reports/quarterly`, { params: this.params({ year, quarter }) });
  }
  exportQuarterly(year: number, quarter: number, format: 'csv' | 'xlsx'): Observable<Blob> {
    return this.http.get(`${this.base}/reports/quarterly/export`, {
      params: this.params({ year, quarter, format }), responseType: 'blob',
    });
  }
}

/** Turns a backend error into a readable message for the UI. */
export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) return 'Cannot reach the server. Is the backend running on port 8000?';
    const d = err.error?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x: any) => `${x.loc?.slice(-1)[0]}: ${x.msg}`).join(', ');
  }
  return 'Something went wrong';
}
