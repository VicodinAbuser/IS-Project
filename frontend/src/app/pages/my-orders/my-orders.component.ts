import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { DeliveryStatus, Order } from '../../core/models';

@Component({
  selector: 'app-my-orders',
  imports: [CurrencyPipe, DatePipe, RouterLink],
  templateUrl: './my-orders.component.html',
  styleUrl: './my-orders.component.scss',
})
export class MyOrdersComponent implements OnInit {
  private api = inject(ApiService);
  orders = signal<Order[]>([]);
  error = signal('');
  steps: DeliveryStatus[] = ['PACKED', 'SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED'];

  ngOnInit() { this.load(); }

  load() { this.api.myOrders().subscribe({ next: o => this.orders.set(o), error: e => this.error.set(errorMessage(e)) }); }

  stepIndex(o: Order) { return this.steps.indexOf(o.delivery?.status as DeliveryStatus); }

  canCancel(o: Order) {
    return o.status !== 'CANCELLED' && ['NOT_SHIPPED', 'PACKED'].includes(o.delivery?.status ?? '');
  }

  cancel(o: Order) {
    if (!confirm(`Cancel order #${o.id}?`)) return;
    this.api.cancelOrder(o.id).subscribe({ next: () => this.load(), error: e => this.error.set(errorMessage(e)) });
  }

  label(s: string) { return s.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()); }
}
