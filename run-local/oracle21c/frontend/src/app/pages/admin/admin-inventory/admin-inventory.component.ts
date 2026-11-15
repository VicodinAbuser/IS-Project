import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../../core/api.service';
import { InventoryRow, Outlet, Product, StockMovement } from '../../../core/models';

type Action = 'restock' | 'adjust' | 'transfer';

@Component({
  selector: 'app-admin-inventory',
  imports: [FormsModule, CurrencyPipe, DatePipe, DecimalPipe],
  templateUrl: './admin-inventory.component.html',
  styleUrl: './admin-inventory.component.scss',
})
export class AdminInventoryComponent implements OnInit {
  private api = inject(ApiService);
  outlets = signal<Outlet[]>([]);
  products = signal<Product[]>([]);
  rows = signal<InventoryRow[]>([]);
  summary = signal<any>(null);
  movements = signal<StockMovement[]>([]);
  view = signal<'outlet' | 'collective' | 'log'>('outlet');
  outletFilter: number | null = null;
  lowOnly = signal(false);
  shownRows = computed(() => (this.lowOnly() ? this.rows().filter(r => r.low_stock) : this.rows()));

  action: Action = 'restock';
  f = { product_id: null as number | null, outlet_id: null as number | null, to_outlet_id: null as number | null, quantity: 10, note: '' };
  message = signal('');
  error = signal('');

  ngOnInit() {
    this.api.getOutlets().subscribe(o => this.outlets.set(o));
    this.api.getProducts().subscribe(p => this.products.set(p));
    this.refresh();
  }

  refresh() {
    this.api.getInventory(this.outletFilter ?? undefined).subscribe(r => this.rows.set(r));
    this.api.getInventorySummary().subscribe(s => this.summary.set(s));
    this.api.getMovements(100).subscribe(m => this.movements.set(m));
  }

  pick(r: InventoryRow) {
    this.f.product_id = r.product_id;
    this.f.outlet_id = r.outlet_id;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  submit() {
    const { product_id, outlet_id, to_outlet_id, quantity, note } = this.f;
    if (!product_id || !outlet_id) { this.error.set('Choose a product and an outlet'); return; }
    const req =
      this.action === 'restock' ? this.api.restock({ product_id, outlet_id, quantity, note: note || 'New stock received' }) :
      this.action === 'adjust' ? this.api.adjust({ product_id, outlet_id, change: quantity, note: note || 'Manual adjustment' }) :
      this.api.transfer({ product_id, from_outlet_id: outlet_id, to_outlet_id: to_outlet_id!, quantity, note });
    req.subscribe({
      next: () => { this.message.set('Inventory updated'); this.error.set(''); this.refresh(); setTimeout(() => this.message.set(''), 2500); },
      error: e => { this.error.set(errorMessage(e)); this.message.set(''); },
    });
  }
}
