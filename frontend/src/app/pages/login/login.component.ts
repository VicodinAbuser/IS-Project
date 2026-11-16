import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent implements OnInit {
  private auth = inject(AuthService);
  private api = inject(ApiService);
  private router = inject(Router);
  expired = input<string>();            // ?expired=1 when the session ran out
  error = signal('');
  loading = signal(false);
  showPassword = signal(false);
  serverStatus = signal<'checking' | 'ok' | 'nodb' | 'fail'>('checking');
  oracleVersion = signal('');

  // Typed in by the user: nothing is filled in automatically.
  form = inject(FormBuilder).nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  ngOnInit() { this.testServer(); }

  /** Is the backend (and, through it, Oracle) reachable? */
  testServer() {
    this.serverStatus.set('checking');
    this.api.health().subscribe({
      next: h => { this.oracleVersion.set(h.oracle_version); this.serverStatus.set('ok'); },
      error: err => this.serverStatus.set(err.status === 503 ? 'nodb' : 'fail'),
    });
  }

  submit() {
    if (this.form.invalid) return;
    this.loading.set(true);
    this.error.set('');
    const { email, password } = this.form.getRawValue();
    this.auth.login(email.trim(), password).subscribe({
      next: user => this.router.navigateByUrl(this.auth.homePath(user)),
      error: err => {
        this.error.set(errorMessage(err));
        this.loading.set(false);
        this.form.controls.password.reset();
      },
    });
  }
}
