import { Routes } from '@angular/router';
import { authGuard, guestGuard, permissionGuard } from './core/guards';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { ShopComponent } from './pages/shop/shop.component';
import { CartComponent } from './pages/cart/cart.component';
import { CheckoutComponent } from './pages/checkout/checkout.component';
import { MyOrdersComponent } from './pages/my-orders/my-orders.component';
import { ProfileComponent } from './pages/profile/profile.component';
import { AdminDashboardComponent } from './pages/admin/admin-dashboard/admin-dashboard.component';
import { AdminProductsComponent } from './pages/admin/admin-products/admin-products.component';
import { AdminInventoryComponent } from './pages/admin/admin-inventory/admin-inventory.component';
import { AdminOrdersComponent } from './pages/admin/admin-orders/admin-orders.component';
import { AdminReportsComponent } from './pages/admin/admin-reports/admin-reports.component';
import { AdminUsersComponent } from './pages/admin/admin-users/admin-users.component';

// Each page names the permission it needs (see the PERMISSIONS / AUTHORIZATIONS tables).
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'shop' },
  { path: 'login', component: LoginComponent, canActivate: [guestGuard], title: 'Login' },
  { path: 'register', component: RegisterComponent, canActivate: [guestGuard], title: 'Register' },
  // Shopping
  { path: 'shop', component: ShopComponent, canActivate: [permissionGuard('CATALOG_READ')], title: 'Shop' },
  { path: 'cart', component: CartComponent, canActivate: [permissionGuard('ORDER_PLACE')], title: 'Cart' },
  { path: 'checkout/:id', component: CheckoutComponent, canActivate: [authGuard], title: 'Payment' },
  { path: 'orders', component: MyOrdersComponent, canActivate: [permissionGuard('ORDER_READ_OWN')], title: 'My orders' },
  { path: 'profile', component: ProfileComponent, canActivate: [authGuard], title: 'My profile' },
  // Staff pages
  {
    path: 'admin', children: [
      { path: '', component: AdminDashboardComponent, canActivate: [permissionGuard('REPORT_VIEW')], title: 'Dashboard' },
      { path: 'products', component: AdminProductsComponent, canActivate: [permissionGuard('CATALOG_WRITE')], title: 'Products' },
      { path: 'inventory', component: AdminInventoryComponent, canActivate: [permissionGuard('STOCK_READ')], title: 'Inventory' },
      { path: 'orders', component: AdminOrdersComponent, canActivate: [permissionGuard('ORDER_READ_ALL')], title: 'Orders' },
      { path: 'reports', component: AdminReportsComponent, canActivate: [permissionGuard('REPORT_VIEW')], title: 'Reports' },
      { path: 'users', component: AdminUsersComponent, canActivate: [permissionGuard('USER_READ')], title: 'Users & access' },
    ],
  },
  { path: '**', redirectTo: 'shop' },
];
