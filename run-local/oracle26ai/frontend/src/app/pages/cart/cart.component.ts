import { CurrencyPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { CartService } from '../../core/cart.service';
import { Outlet } from '../../core/models';

@Component({
  selector: 'app-cart',
  imports: [CurrencyPipe, FormsModule, RouterLink],
  templateUrl: './cart.component.html',
  styleUrl: './cart.component.scss',
})
export class CartComponent implements OnInit {
  private api = inject(ApiService);
  private router = inject(Router);
  cart = inject(CartService);
  outlet = signal<Outlet | undefined>(undefined);
  error = signal('');
  placing = signal(false);
  address = inject(AuthService).user()?.address ?? '';

  ngOnInit() {
    this.api.getOutlets().subscribe(o => this.outlet.set(o.find(x => x.id === this.cart.outletId())));
  }

  placeOrder() {
    const outletId = this.cart.outletId();
    if (!outletId) { this.error.set('Pick an outlet in the shop first'); return; }
    this.placing.set(true);
    this.error.set('');
    this.api.placeOrder({
      outlet_id: outletId,
      shipping_address: this.address,
      items: this.cart.items().map(i => ({ product_id: i.product.id, quantity: i.quantity })),
    }).subscribe({
      next: order => { this.cart.clear(); this.router.navigate(['/checkout', order.id]); },
      error: e => { this.error.set(errorMessage(e)); this.placing.set(false); },
    });
  }
}
