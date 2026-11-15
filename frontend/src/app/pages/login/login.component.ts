import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  error = signal('');
  loading = signal(false);

  form = inject(FormBuilder).nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  fillDemo(role: 'admin' | 'customer') {
    this.form.setValue(role === 'admin'
      ? { email: 'admin@inventory.com', password: 'admin123' }
      : { email: 'customer@inventory.com', password: 'customer123' });
  }

  submit() {
    if (this.form.invalid) return;
    this.loading.set(true);
    this.error.set('');
    const { email, password } = this.form.getRawValue();
    this.auth.login(email, password).subscribe({
      next: res => this.router.navigate([res.user.role === 'ADMIN' ? '/admin' : '/shop']),
      error: err => { this.error.set(errorMessage(err)); this.loading.set(false); },
    });
  }
}
