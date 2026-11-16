import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Outlet } from '../../core/models';

/** The logged-in user's own details, profiles and permissions. Customers can edit their delivery details. */
@Component({
  selector: 'app-profile',
  imports: [ReactiveFormsModule],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss',
})
export class ProfileComponent implements OnInit {
  auth = inject(AuthService);
  private api = inject(ApiService);
  outlets = signal<Outlet[]>([]);
  message = signal('');
  error = signal('');

  form = inject(FormBuilder).nonNullable.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    phone: ['', Validators.pattern(/^[0-9+\- ]{8,20}$/)],
    address_line: [''],
    city: [''],
    state: [''],
    pincode: ['', Validators.pattern(/^[0-9]{6}$/)],
    preferred_outlet_id: [null as number | null],
  });

  ngOnInit() {
    const u = this.auth.user()!;
    this.form.setValue({ name: u.name, phone: u.phone ?? '', address_line: u.address_line ?? '', city: u.city ?? '',
      state: u.state ?? '', pincode: u.pincode ?? '', preferred_outlet_id: u.preferred_outlet_id ?? null });
    this.api.getOutlets().subscribe(o => this.outlets.set(o));
  }

  isCustomer() { return this.auth.user()?.profiles.includes('CUSTOMER') ?? false; }

  save() {
    if (this.form.invalid) return;
    this.api.updateMe(this.form.getRawValue()).subscribe({
      next: u => { this.auth.user.set(u); this.message.set('Saved'); this.error.set(''); setTimeout(() => this.message.set(''), 2500); },
      error: e => { this.error.set(errorMessage(e)); this.message.set(''); },
    });
  }

  label(code: string) { return code.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()); }
}
