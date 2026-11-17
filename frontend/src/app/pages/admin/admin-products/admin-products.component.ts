import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService, errorMessage } from '../../../core/api.service';
import { Category, Choice, Product, Supplier, UPDATED_WITHIN } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

const DEFAULT_FILTER = { search: '', sort: 'updated_desc', updated_within_days: null as number | null, include_inactive: true };

@Component({
  selector: 'app-admin-products',
  imports: [CurrencyPipe, DatePipe, ReactiveFormsModule, FormsModule],
  templateUrl: './admin-products.component.html',
  styleUrl: './admin-products.component.scss',
})
export class AdminProductsComponent implements OnInit {
  private api = inject(ApiService);
  products = signal<Product[]>([]);
  categories = signal<Category[]>([]);
  suppliers = signal<Supplier[]>([]);
  editingId = signal<number | null>(null);
  showForm = signal(false);
  error = signal('');
  message = signal('');
  filter = { ...DEFAULT_FILTER };
  private toast = inject(ToastService);
  sorts: Choice[] = [
    { value: 'updated_desc', label: 'Latest updated' }, { value: 'newest', label: 'Newest products' },
    { value: 'name_asc', label: 'Name A–Z' }, { value: 'price_asc', label: 'Price: low to high' },
    { value: 'price_desc', label: 'Price: high to low' },
  ];
  within = UPDATED_WITHIN;

  form = inject(FormBuilder).group({
    sku: ['', [Validators.required, Validators.minLength(2)]],
    name: ['', [Validators.required, Validators.minLength(2)]],
    description: [''],
    price: [0, [Validators.required, Validators.min(0)]],
    image_url: [''],
    reorder_level: [10, [Validators.required, Validators.min(0)]],
    category_id: [null as number | null],
    supplier_id: [null as number | null],
    is_active: [true],
  });

  ngOnInit() {
    this.load();
    this.api.getCategories().subscribe(c => this.categories.set(c));
    this.api.getSuppliers().subscribe(s => this.suppliers.set(s));
  }

  load() { this.api.getProducts(this.filter).subscribe(p => this.products.set(p)); }

  /** Is any filter different from the default? (enables the Reset button) */
  filtersActive() { return JSON.stringify(this.filter) !== JSON.stringify(DEFAULT_FILTER); }

  resetFilters() {
    this.filter = { ...DEFAULT_FILTER };
    this.load();
  }


  newProduct() {
    this.editingId.set(null);
    this.form.reset({ price: 0, reorder_level: 10, is_active: true, category_id: null, supplier_id: null });
    this.showForm.set(true);
  }

  edit(p: Product) {
    this.editingId.set(p.id);
    this.form.setValue({ sku: p.sku, name: p.name, description: p.description ?? '', price: p.price,
      image_url: p.image_url ?? '', reorder_level: p.reorder_level, category_id: p.category?.id ?? null,
      supplier_id: p.supplier?.id ?? null, is_active: p.is_active });
    this.showForm.set(true);
  }

  save() {
    if (this.form.invalid) return;
    const body = this.form.getRawValue() as any;
    const id = this.editingId();
    const req = id ? this.api.updateProduct(id, body) : this.api.createProduct(body);
    req.subscribe({
      next: p => { this.toast.success(`Saved ${p.name}`); this.showForm.set(false); this.error.set(''); this.load(); },
      error: e => this.error.set(errorMessage(e)),
    });
  }

  deactivate(p: Product) {
    if (!confirm(`Hide "${p.name}" from the shop?`)) return;
    this.api.deactivateProduct(p.id).subscribe(() => { this.toast.success(`${p.name} is now hidden from the shop`); this.load(); });
  }
}
