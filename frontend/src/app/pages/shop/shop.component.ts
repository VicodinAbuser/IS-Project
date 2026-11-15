import { CurrencyPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../core/api.service';
import { CartService } from '../../core/cart.service';
import { Category, Outlet, Product } from '../../core/models';

@Component({
  selector: 'app-shop',
  imports: [FormsModule, CurrencyPipe],
  templateUrl: './shop.component.html',
  styleUrl: './shop.component.scss',
})
export class ShopComponent implements OnInit {
  private api = inject(ApiService);
  cart = inject(CartService);

  products = signal<Product[]>([]);
  outlets = signal<Outlet[]>([]);
  categories = signal<Category[]>([]);
  error = signal('');
  added = signal<number | null>(null);
  search = '';
  categoryId: number | null = null;
  outletId: number | null = this.cart.outletId();

  ngOnInit() {
    this.api.getOutlets().subscribe(o => {
      this.outlets.set(o);
      if (!this.outletId && o.length) this.outletId = o[0].id;
      this.load();
    });
    this.api.getCategories().subscribe(c => this.categories.set(c));
  }

  load() {
    this.api.getProducts({ search: this.search, category_id: this.categoryId ?? undefined, outlet_id: this.outletId ?? undefined })
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
