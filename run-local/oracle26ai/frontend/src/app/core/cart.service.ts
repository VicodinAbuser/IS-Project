import { Injectable, computed, effect, signal } from '@angular/core';
import { CartItem, Product } from './models';

/** Shopping cart kept in the browser (localStorage) until the customer checks out. */
@Injectable({ providedIn: 'root' })
export class CartService {
  readonly items = signal<CartItem[]>(this.load());
  readonly outletId = signal<number | null>(Number(localStorage.getItem('ims_cart_outlet')) || null);
  readonly count = computed(() => this.items().reduce((n, i) => n + i.quantity, 0));
  readonly total = computed(() => this.items().reduce((s, i) => s + i.quantity * i.product.price, 0));

  constructor() {
    effect(() => {
      localStorage.setItem('ims_cart', JSON.stringify(this.items()));
      const o = this.outletId();
      o ? localStorage.setItem('ims_cart_outlet', String(o)) : localStorage.removeItem('ims_cart_outlet');
    });
  }

  add(product: Product, qty = 1): void {
    this.items.update(items => {
      const found = items.find(i => i.product.id === product.id);
      return found
        ? items.map(i => (i.product.id === product.id ? { ...i, quantity: i.quantity + qty } : i))
        : [...items, { product, quantity: qty }];
    });
  }

  setQuantity(productId: number, qty: number): void {
    if (qty <= 0) return this.remove(productId);
    this.items.update(items => items.map(i => (i.product.id === productId ? { ...i, quantity: qty } : i)));
  }

  remove(productId: number): void {
    this.items.update(items => items.filter(i => i.product.id !== productId));
  }

  clear(): void {
    this.items.set([]);
  }

  private load(): CartItem[] {
    try { return JSON.parse(localStorage.getItem('ims_cart') || '[]'); } catch { return []; }
  }
}
