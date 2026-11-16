import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../../core/api.service';
import { AuthService } from '../../../core/auth.service';
import { Choice, InventoryRow, Outlet, Product, StockMovement, UPDATED_WITHIN } from '../../../core/models';

type Action = 'restock' | 'adjust' | 'transfer';

@Component({
  selector: 'app-admin-inventory',
  imports: [FormsModule, CurrencyPipe, DatePipe, DecimalPipe],
  templateUrl: './admin-inventory.component.html',
  styleUrl: './admin-inventory.component.scss',
})
export class AdminInventoryComponent implements OnInit {
  private api = inject(ApiService);
  auth = inject(AuthService);
  outlets = signal<Outlet[]>([]);
  products = signal<Product[]>([]);
  rows = signal<InventoryRow[]>([]);
  summary = signal<any>(null);
  movements = signal<StockMovement[]>([]);
  view = signal<'outlet' | 'collective' | 'log'>('outlet');
  within = UPDATED_WITHIN;

  // Stock list: filtering and sorting are done by the database (GET /api/inventory?sort=...)
  stockFilter = { outlet_id: null as number | null, low_only: false, search: '', sort: 'outlet_asc',
                  updated_within_days: null as number | null };
  stockSorts: Choice[] = [
    { value: 'outlet_asc', label: 'Outlet, then product' }, { value: 'updated_desc', label: 'Latest updated' },
    { value: 'quantity_asc', label: 'Quantity: low to high' }, { value: 'quantity_desc', label: 'Quantity: high to low' },
    { value: 'product_asc', label: 'Product A–Z' }, { value: 'updated_asc', label: 'Least recently updated' },
  ];
  // Movement log
  logFilter = { movement_type: '', outlet_id: null as number | null, search: '', sort: 'newest',
                updated_within_days: null as number | null, limit: 100 };
  logSorts: Choice[] = [
    { value: 'newest', label: 'Newest first' }, { value: 'oldest', label: 'Oldest first' },
    { value: 'change_desc', label: 'Biggest change' },
  ];
  types = ['RESTOCK', 'SALE', 'CANCEL', 'RETURN', 'ADJUSTMENT', 'TRANSFER_IN', 'TRANSFER_OUT', 'MANUAL'];

  action: Action = 'restock';
  f = { product_id: null as number | null, outlet_id: null as number | null, to_outlet_id: null as number | null, quantity: 10, note: '' };
  message = signal('');
  error = signal('');

  ngOnInit() {
    this.api.getOutlets().subscribe(o => this.outlets.set(o));
    this.api.getProducts({ sort: 'name_asc' }).subscribe(p => this.products.set(p));
    this.refresh();
  }

  refresh() {
    this.loadStock();
    this.api.getInventorySummary().subscribe(s => this.summary.set(s));
    this.loadLog();
  }

  loadStock() {
    this.api.getInventory(this.stockFilter).subscribe({ next: r => this.rows.set(r), error: e => this.error.set(errorMessage(e)) });
  }

  loadLog() {
    this.api.getMovements(this.logFilter).subscribe({ next: m => this.movements.set(m), error: e => this.error.set(errorMessage(e)) });
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
