import { Routes } from '@angular/router';
import { adminGuard, authGuard, guestGuard } from './core/guards';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { ShopComponent } from './pages/shop/shop.component';
import { CartComponent } from './pages/cart/cart.component';
import { CheckoutComponent } from './pages/checkout/checkout.component';
import { MyOrdersComponent } from './pages/my-orders/my-orders.component';
import { AdminDashboardComponent } from './pages/admin/admin-dashboard/admin-dashboard.component';
import { AdminProductsComponent } from './pages/admin/admin-products/admin-products.component';
import { AdminInventoryComponent } from './pages/admin/admin-inventory/admin-inventory.component';
import { AdminOrdersComponent } from './pages/admin/admin-orders/admin-orders.component';
import { AdminReportsComponent } from './pages/admin/admin-reports/admin-reports.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'shop' },
  { path: 'login', component: LoginComponent, canActivate: [guestGuard], title: 'Login' },
  { path: 'register', component: RegisterComponent, canActivate: [guestGuard], title: 'Register' },
  // Customer pages (admins can also shop)
  { path: 'shop', component: ShopComponent, canActivate: [authGuard], title: 'Shop' },
  { path: 'cart', component: CartComponent, canActivate: [authGuard], title: 'Cart' },
  { path: 'checkout/:id', component: CheckoutComponent, canActivate: [authGuard], title: 'Payment' },
  { path: 'orders', component: MyOrdersComponent, canActivate: [authGuard], title: 'My orders' },
  // Admin-only pages
  {
    path: 'admin', canActivate: [adminGuard], children: [
      { path: '', component: AdminDashboardComponent, title: 'Admin dashboard' },
      { path: 'products', component: AdminProductsComponent, title: 'Products' },
      { path: 'inventory', component: AdminInventoryComponent, title: 'Inventory' },
      { path: 'orders', component: AdminOrdersComponent, title: 'Orders' },
      { path: 'reports', component: AdminReportsComponent, title: 'Reports' },
    ],
  },
  { path: '**', redirectTo: 'shop' },
];
