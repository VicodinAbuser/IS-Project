import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  it('stores the token and user after login', () => {
    auth.login('admin@inventory.com', 'admin123').subscribe();
    const req = http.expectOne(`${environment.apiUrl}/auth/login`);
    expect(req.request.method).toBe('POST');
    req.flush({ access_token: 'abc', token_type: 'bearer', user: { id: 1, name: 'A', email: 'a@x.com', role: 'ADMIN' } });
    expect(auth.token).toBe('abc');
    expect(auth.isAdmin()).toBeTrue();
  });

  it('clears everything on logout', () => {
    localStorage.setItem('ims_token', 'abc');
    auth.logout();
    expect(auth.token).toBeNull();
    expect(auth.isLoggedIn()).toBeFalse();
  });
});
