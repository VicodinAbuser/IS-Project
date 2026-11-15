import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../environments/environment';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  it('sends filters as query parameters and skips empty ones', () => {
    api.getProducts({ search: 'mouse', outlet_id: 2, category_id: undefined }).subscribe();
    const req = http.expectOne(r => r.url === `${environment.apiUrl}/products`);
    expect(req.request.params.get('search')).toBe('mouse');
    expect(req.request.params.get('outlet_id')).toBe('2');
    expect(req.request.params.has('category_id')).toBeFalse();
  });

  it('posts a restock to the inventory endpoint', () => {
    api.restock({ product_id: 1, outlet_id: 1, quantity: 5 }).subscribe();
    const req = http.expectOne(`${environment.apiUrl}/inventory/restock`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body.quantity).toBe(5);
  });
});
