import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../../core/api.service';
import { Dashboard, InventoryRow, Order } from '../../../core/models';

@Component({
  selector: 'app-admin-dashboard',
  imports: [CurrencyPipe, DecimalPipe, RouterLink],
  templateUrl: './admin-dashboard.component.html',
  styleUrl: './admin-dashboard.component.scss',
})
export class AdminDashboardComponent implements OnInit {
  private api = inject(ApiService);
  stats = signal<Dashboard | null>(null);
  lowStock = signal<InventoryRow[]>([]);
  toShip = signal<Order[]>([]);

  ngOnInit() {
    this.api.getDashboard().subscribe(s => this.stats.set(s));
    this.api.getLowStock().subscribe(l => this.lowStock.set(l));
    this.api.allOrders({ status: 'PAID', delivery_status: 'PACKED' }).subscribe(o => this.toShip.set(o.slice(0, 8)));
  }
}
