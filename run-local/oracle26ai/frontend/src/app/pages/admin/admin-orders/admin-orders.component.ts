import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../../core/api.service';
import { AuthService } from '../../../core/auth.service';
import { Choice, DeliveryStatus, Order, Outlet, UPDATED_WITHIN } from '../../../core/models';

@Component({
  selector: 'app-admin-orders',
  imports: [CurrencyPipe, DatePipe, FormsModule],
  templateUrl: './admin-orders.component.html',
  styleUrl: './admin-orders.component.scss',
})
export class AdminOrdersComponent implements OnInit {
  private api = inject(ApiService);
  auth = inject(AuthService);
  orders = signal<Order[]>([]);
  loading = signal(false);
  outlets = signal<Outlet[]>([]);
  error = signal('');
  filter = { status: '', outlet_id: null as number | null, delivery_status: '', search: '',
             sort: 'updated_desc', updated_within_days: null as number | null, limit: 100 };
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

  saveDelivery(o: Order) {
    this.api.updateDelivery(o.id, this.edits[o.id]).subscribe({
      next: updated => this.orders.update(list => list.map(x => (x.id === o.id ? updated : x))),
      error: e => this.error.set(errorMessage(e)),
    });
  }

  cancel(o: Order) {
    if (!confirm(`Cancel order #${o.id}? Stock will be returned to ${o.outlet.name}.`)) return;
    this.api.cancelOrder(o.id).subscribe({ next: () => this.load(), error: e => this.error.set(errorMessage(e)) });
  }

  label(s?: string) { return (s ?? '').replace(/_/g, ' '); }
}
