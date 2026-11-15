import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

/** UI-side route protection. (The backend enforces the same rules, so this is for UX only.) */
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isLoggedIn() || inject(Router).createUrlTree(['/login']);
};

export const adminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  if (!auth.isLoggedIn()) return inject(Router).createUrlTree(['/login']);
  return auth.isAdmin() || inject(Router).createUrlTree(['/shop']);
};

export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  if (!auth.isLoggedIn()) return true;
  return inject(Router).createUrlTree([auth.isAdmin() ? '/admin' : '/shop']);
};
