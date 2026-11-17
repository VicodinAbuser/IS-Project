import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../../core/api.service';
import { AuthService } from '../../../core/auth.service';
import { Choice, DeliveryStatus, Order, Outlet, UPDATED_WITHIN } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

const DEFAULT_FILTER = { status: '', outlet_id: null as number | null, delivery_status: '', search: '',
                         sort: 'updated_desc', updated_within_days: null as number | null, limit: 100 };

@Component({
  selector: 'app-admin-orders',
  imports: [CurrencyPipe, DatePipe, FormsModule],
  templateUrl: './admin-orders.component.html',
  styleUrl: './admin-orders.component.scss',
})
export class AdminOrdersComponent implements OnInit {
  private api = inject(ApiService);
  auth = inject(AuthService);
  private toast = inject(ToastService);
  orders = signal<Order[]>([]);
  loading = signal(false);
  outlets = signal<Outlet[]>([]);
  error = signal('');
  filter = { ...DEFAULT_FILTER };
  sorts: Choice[] = [
    { value: 'updated_desc', label: 'Latest updated' }, { value: 'created_desc', label: 'Newest orders' },
    { value: 'created_asc', label: 'Oldest orders' }, { value: 'amount_desc', label: 'Amount: high to low' },
    { value: 'amount_asc', label: 'Amount: low to high' }, { value: 'updated_asc', label: 'Least recently updated' },
  ];
  within = UPDATED_WITHIN;
  deliveryStatuses: DeliveryStatus[] = ['PACKED', 'SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED', 'RETURNED'];
  edits: Record<number, { status: DeliveryStatus; courier: string; tracking_number: string }> = {};

  ngOnInit() {
    this.api.getOutlets().subscribe(o => this.outlets.set(o));
    this.load();
  }

  load() {
    this.loading.set(true);
    this.api.allOrders(this.filter).subscribe({
      next: list => {
        this.loading.set(false);
        this.orders.set(list);
        for (const o of list) this.edits[o.id] = {
          status: (o.delivery?.status ?? 'PACKED') as DeliveryStatus,
          courier: o.delivery?.courier ?? '', tracking_number: o.delivery?.tracking_number ?? '',
        };
      },
      error: e => { this.error.set(errorMessage(e)); this.loading.set(false); },
    });
  }

  /** Is any filter different from the default? (enables the Reset button) */
  filtersActive() { return JSON.stringify(this.filter) !== JSON.stringify(DEFAULT_FILTER); }

  resetFilters() {
    this.filter = { ...DEFAULT_FILTER };
    this.load();
  }

  saveDelivery(o: Order) {
    const before = o.delivery?.status;
    this.api.updateDelivery(o.id, this.edits[o.id]).subscribe({
      next: updated => {
        this.orders.update(list => list.map(x => (x.id === o.id ? updated : x)));
        this.error.set('');
        const now = updated.delivery?.status;
        this.toast.success(now !== before
          ? `Order #${o.id}: delivery status updated to ${this.label(now)}`
          : `Order #${o.id}: delivery details saved`);
        if (now === 'RETURNED') this.toast.info(`Order #${o.id}: stock returned to ${o.outlet.name} and payment refunded`);
      },
      error: e => this.toast.error(`Order #${o.id}: ${errorMessage(e)}`),
    });
  }

  cancel(o: Order) {
    if (!confirm(`Cancel order #${o.id}? Stock will be returned to ${o.outlet.name}.`)) return;
    this.api.cancelOrder(o.id).subscribe({
      next: r => { this.toast.success(`Order #${o.id} cancelled; payment ${r.payment?.status?.toLowerCase()}`); this.load(); },
      error: e => this.toast.error(`Order #${o.id}: ${errorMessage(e)}`),
    });
  }

  label(s?: string) { return (s ?? '').replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()); }
}
