import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { Choice, DeliveryStatus, Order, UPDATED_WITHIN } from '../../core/models';
import { ToastService } from '../../core/toast.service';

const DEFAULT_FILTER = { sort: 'updated_desc', status: '', updated_within_days: null as number | null };

@Component({
  selector: 'app-my-orders',
  imports: [CurrencyPipe, DatePipe, RouterLink, FormsModule],
  templateUrl: './my-orders.component.html',
  styleUrl: './my-orders.component.scss',
})
export class MyOrdersComponent implements OnInit {
  private api = inject(ApiService);
  orders = signal<Order[]>([]);
  error = signal('');
  steps: DeliveryStatus[] = ['PACKED', 'SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED'];
  filter = { ...DEFAULT_FILTER };
  private toast = inject(ToastService);
  sorts: Choice[] = [
    { value: 'updated_desc', label: 'Latest update first' }, { value: 'created_desc', label: 'Newest orders first' },
    { value: 'created_asc', label: 'Oldest orders first' }, { value: 'amount_desc', label: 'Amount: high to low' },
  ];
  within = UPDATED_WITHIN;

  ngOnInit() { this.load(); }

  /** Is any filter different from the default? (enables the Reset button) */
  filtersActive() { return JSON.stringify(this.filter) !== JSON.stringify(DEFAULT_FILTER); }

  resetFilters() {
    this.filter = { ...DEFAULT_FILTER };
    this.load();
  }


  load() { this.api.myOrders(this.filter).subscribe({ next: o => this.orders.set(o), error: e => this.error.set(errorMessage(e)) }); }

  stepIndex(o: Order) { return this.steps.indexOf(o.delivery?.status as DeliveryStatus); }

  canCancel(o: Order) {
    return o.status !== 'CANCELLED' && ['NOT_SHIPPED', 'PACKED'].includes(o.delivery?.status ?? '');
  }

  cancel(o: Order) {
    if (!confirm(`Cancel order #${o.id}?`)) return;
    this.api.cancelOrder(o.id).subscribe({
      next: () => { this.toast.success(`Order #${o.id} cancelled`); this.load(); },
      error: e => this.toast.error(errorMessage(e)),
    });
  }

  label(s: string) { return s.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()); }
}
