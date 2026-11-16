import { CurrencyPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../core/api.service';
import { CartService } from '../../core/cart.service';
import { AuthService } from '../../core/auth.service';
import { Category, Choice, Outlet, Product } from '../../core/models';

@Component({
  selector: 'app-shop',
  imports: [FormsModule, CurrencyPipe],
  templateUrl: './shop.component.html',
  styleUrl: './shop.component.scss',
})
export class ShopComponent implements OnInit {
  private api = inject(ApiService);
  cart = inject(CartService);
  private auth = inject(AuthService);

  products = signal<Product[]>([]);
  outlets = signal<Outlet[]>([]);
  categories = signal<Category[]>([]);
  error = signal('');
  added = signal<number | null>(null);
  search = '';
  categoryId: number | null = null;
  sort = 'name_asc';
  sorts: Choice[] = [
    { value: 'name_asc', label: 'Name A–Z' }, { value: 'price_asc', label: 'Price: low to high' },
    { value: 'price_desc', label: 'Price: high to low' }, { value: 'newest', label: 'Newest arrivals' },
  ];
  // Start with the cart's outlet, else the customer's nearest outlet from their profile.
  outletId: number | null = this.cart.outletId() ?? this.auth.user()?.preferred_outlet_id ?? null;

  ngOnInit() {
    this.api.getOutlets().subscribe(o => {
      this.outlets.set(o);
      if (!this.outletId && o.length) this.outletId = o[0].id;
      this.load();
    });
    this.api.getCategories().subscribe(c => this.categories.set(c));
  }

  load() {
    this.api.getProducts({ search: this.search, category_id: this.categoryId ?? undefined, outlet_id: this.outletId ?? undefined, sort: this.sort })
      .subscribe({ next: p => this.products.set(p), error: e => this.error.set(errorMessage(e)) });
  }

  changeOutlet() {
    // Stock differs per outlet, so the cart is tied to one outlet.
    if (this.cart.outletId() !== this.outletId) this.cart.clear();
    this.cart.outletId.set(this.outletId);
    this.load();
  }

  inCart(id: number) { return this.cart.items().find(i => i.product.id === id)?.quantity ?? 0; }

  add(p: Product) {
    this.cart.outletId.set(this.outletId);
    this.cart.add(p);
    this.added.set(p.id);
    setTimeout(() => this.added.set(null), 1200);
  }
}
