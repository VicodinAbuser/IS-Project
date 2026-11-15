import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AdminInventoryComponent } from './admin-inventory.component';

describe('AdminInventoryComponent', () => {
  let fixture: ComponentFixture<AdminInventoryComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminInventoryComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(AdminInventoryComponent);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });
});
