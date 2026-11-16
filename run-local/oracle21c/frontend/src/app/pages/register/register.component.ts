import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Outlet } from '../../core/models';

/** Customer sign-up: creates a USERS row, a CUSTOMER_PROFILES row and the CUSTOMER profile. */
@Component({
  selector: 'app-register',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
})
export class RegisterComponent implements OnInit {
  private auth = inject(AuthService);
  private api = inject(ApiService);
  private router = inject(Router);
  error = signal('');
  saving = signal(false);
  showPassword = signal(false);
  outlets = signal<Outlet[]>([]);

  form = inject(FormBuilder).nonNullable.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    phone: ['', Validators.pattern(/^[0-9+\- ]{8,20}$/)],
    address_line: [''],
    city: [''],
    state: [''],
    pincode: ['', Validators.pattern(/^[0-9]{6}$/)],
    preferred_outlet_id: [null as number | null],
  });

  ngOnInit() { this.api.getOutlets().subscribe(o => this.outlets.set(o)); }

  submit() {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.auth.register(this.form.getRawValue()).subscribe({
      next: () => this.router.navigate(['/shop']),
      error: err => { this.error.set(errorMessage(err)); this.saving.set(false); },
    });
  }
}
