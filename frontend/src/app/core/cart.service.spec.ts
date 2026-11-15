import { TestBed } from '@angular/core/testing';
import { CartService } from './cart.service';
import { Product } from './models';

const product = (id: number, price: number): Product =>
  ({ id, sku: 'S' + id, name: 'P' + id, price, reorder_level: 5, is_active: true, total_stock: 50 });

describe('CartService', () => {
  let cart: CartService;
  beforeEach(() => { localStorage.clear(); cart = TestBed.inject(CartService); });

  it('adds items and merges duplicates', () => {
    cart.add(product(1, 100));
    cart.add(product(1, 100), 2);
    cart.add(product(2, 50));
    expect(cart.items().length).toBe(2);
    expect(cart.count()).toBe(4);
    expect(cart.total()).toBe(350);
  });

  it('removes an item when quantity is set to 0', () => {
    cart.add(product(1, 100));
    cart.setQuantity(1, 0);
    expect(cart.items().length).toBe(0);
  });
});
