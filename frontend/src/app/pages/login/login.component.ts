import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { errorMessage } from '../../core/api.service';
import { apiUrl, isDefaultApiUrl, setApiUrl } from '../../core/api-config';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, FormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private http = inject(HttpClient);
  error = signal('');

  // Which backend this site talks to (useful when the site is on Vercel and the backend is on a laptop).
  server = signal(apiUrl());
  usingDefault = signal(isDefaultApiUrl());
  editingServer = signal(false);
  serverInput = '';
  serverStatus = signal<'idle' | 'checking' | 'ok' | 'nodb' | 'fail'>('idle');
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

  editServer() {
    this.serverInput = this.usingDefault() ? '' : this.server();
    this.editingServer.set(true);
  }

  saveServer(reset = false) {
    setApiUrl(reset ? null : this.serverInput || null);
    this.server.set(apiUrl());
    this.usingDefault.set(isDefaultApiUrl());
    this.editingServer.set(false);
    this.testServer();
  }

  testServer() {
    this.serverStatus.set('checking');
    this.http.get(`${apiUrl()}/health`).subscribe({
      next: () => this.serverStatus.set('ok'),
      error: err => this.serverStatus.set(err.status === 503 ? 'nodb' : 'fail'),
    });
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
