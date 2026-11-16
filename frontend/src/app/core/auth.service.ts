import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { CartService } from './cart.service';
import { AddressFields, LoginResponse, Permission, User } from './models';

/**
 * Who is logged in. The session itself is an HttpOnly cookie set by the backend: this code
 * can't read it (that's the point: a malicious script couldn't steal it either). The browser
 * sends it automatically with every /api request. Here we only keep the user's name, profiles
 * and permissions in memory, loaded from GET /api/auth/me when the app starts.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private cart = inject(CartService);
  private base = environment.apiUrl;

  readonly user = signal<User | null>(null);
  readonly isLoggedIn = computed(() => this.user() !== null);
  readonly isStaff = computed(() => this.user()?.is_staff ?? false);
  readonly isAdmin = computed(() => this.user()?.profiles.includes('ADMIN') ?? false);

  /** Does the logged-in user have this permission? (The backend checks it again on every request.) */
  can(permission: Permission): boolean {
    return this.user()?.permissions.includes(permission) ?? false;
  }

  /** Asks the backend whether the session cookie is still valid. Called once at start-up. */
  restore(): Observable<User | null> {
    return this.http.get<User>(`${this.base}/auth/me`).pipe(
      tap(u => this.user.set(u)),
      catchError(() => { this.user.set(null); return of(null); }),
    );
  }

  login(email: string, password: string): Observable<User> {
    return this.http.post<LoginResponse>(`${this.base}/auth/login`, { email, password })
      .pipe(map(res => res.user), tap(u => this.user.set(u)));
  }

  register(data: { name: string; email: string; password: string } & AddressFields): Observable<User> {
    return this.http.post<LoginResponse>(`${this.base}/auth/register`, data)
      .pipe(map(res => res.user), tap(u => this.user.set(u)));
  }

  logout(): void {
    this.http.post(`${this.base}/auth/logout`, {}).subscribe({ complete: () => this.ended(), error: () => this.ended() });
  }

  /** The backend said the session is missing or expired. */
  sessionExpired(): void {
    if (this.user()) this.ended(true);
  }

  /** The first page to show after login, based on what the user may do. */
  homePath(user = this.user()): string {
    if (!user?.is_staff) return '/shop';
    const can = (p: Permission) => user.permissions.includes(p);
    return can('REPORT_VIEW') ? '/admin' : can('STOCK_READ') ? '/admin/inventory' : can('ORDER_READ_ALL') ? '/admin/orders' : '/shop';
  }

  private ended(expired = false): void {
    this.user.set(null);
    this.cart.clear();
    this.router.navigate(['/login'], expired ? { queryParams: { expired: 1 } } : {});
  }
}
