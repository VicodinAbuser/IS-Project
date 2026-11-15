import { CurrencyPipe } from '@angular/common';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { Order } from '../../core/models';

/** Demo payment gateway page. Real gateways (Razorpay/Stripe) would open their own checkout here. */
@Component({
  selector: 'app-checkout',
  imports: [CurrencyPipe, FormsModule, RouterLink],
  templateUrl: './checkout.component.html',
  styleUrl: './checkout.component.scss',
})
export class CheckoutComponent implements OnInit {
  private api = inject(ApiService);
  id = input.required<string>(); // from route /checkout/:id
  order = signal<Order | null>(null);
  error = signal('');
  paying = signal(false);
  method: 'CARD' | 'UPI' | 'NETBANKING' = 'CARD';
  card = { number: '4111 1111 1111 1111', expiry: '12/29', cvv: '123', name: '' };
  upiId = 'customer@okbank';
  bank = 'HDFC Bank';

  ngOnInit() {
    this.api.getOrder(+this.id()).subscribe({ next: o => this.order.set(o), error: e => this.error.set(errorMessage(e)) });
  }

  pay() {
    this.paying.set(true);
    this.error.set('');
    this.api.pay(+this.id(), { method: this.method, card_number: this.card.number, upi_id: this.upiId }).subscribe({
      next: o => { this.order.set(o); this.paying.set(false); },
      error: e => { this.error.set(errorMessage(e)); this.paying.set(false); },
    });
  }
}
