import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';
import { User } from './models';

const admin: User = {
  id: 1, name: 'A', email: 'a@x.com', role: 'ADMIN', is_staff: true, profiles: ['ADMIN'],
  permissions: ['REPORT_VIEW', 'STOCK_READ', 'USER_MANAGE'],
};
const warehouse: User = { ...admin, role: 'STAFF', profiles: ['WAREHOUSE_STAFF'], permissions: ['STOCK_READ', 'STOCK_WRITE'] };

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  it('keeps the user in memory only: the session is an HttpOnly cookie, never in localStorage', () => {
    auth.login('a@x.com', 'secret').subscribe();
    const req = http.expectOne(`${environment.apiUrl}/auth/login`);
    expect(req.request.method).toBe('POST');
    req.flush({ user: admin, session_expires_in_minutes: 120 });
    expect(auth.isAdmin()).toBeTrue();
    expect(auth.can('USER_MANAGE')).toBeTrue();
    expect(auth.can('ORDER_PLACE')).toBeFalse();
    expect(Object.keys(localStorage).some(k => k.includes('token'))).toBeFalse();
  });

  it('sends each kind of user to the first page they may open', () => {
    expect(auth.homePath(admin)).toBe('/admin');
    expect(auth.homePath(warehouse)).toBe('/admin/inventory');
    expect(auth.homePath({ ...admin, is_staff: false, profiles: ['CUSTOMER'] })).toBe('/shop');
  });

  it('restores the session from /auth/me and treats a 401 as logged out', () => {
    let result: User | null | undefined;
    auth.restore().subscribe(u => (result = u));
    http.expectOne(`${environment.apiUrl}/auth/me`).flush({ detail: 'no session' }, { status: 401, statusText: 'Unauthorized' });
    expect(result).toBeNull();
    expect(auth.isLoggedIn()).toBeFalse();
  });

  it('clears the user on logout', () => {
    auth.user.set(admin);
    auth.logout();
    http.expectOne(`${environment.apiUrl}/auth/logout`).flush(null);
    expect(auth.isLoggedIn()).toBeFalse();
  });
});
