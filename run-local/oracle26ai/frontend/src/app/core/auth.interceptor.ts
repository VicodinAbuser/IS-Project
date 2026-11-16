import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

/**
 * Runs for every request to the backend API:
 *  - adds "X-Requested-With: XMLHttpRequest". The backend refuses data changes without it,
 *    because another website can't add this header to a request it forges (CSRF protection).
 *  - adds "ngrok-skip-browser-warning", so the free ngrok tunnel answers the API directly.
 * The login cookie is attached by the browser itself (same address, HttpOnly), not by this code.
 * A 401 answer means the session ended: the user is sent back to the login page.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(environment.apiUrl)) return next(req);
  const auth = inject(AuthService);
  const apiReq = req.clone({
    setHeaders: { 'X-Requested-With': 'XMLHttpRequest', 'ngrok-skip-browser-warning': 'true' },
  });
  return next(apiReq).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status === 401 && !req.url.includes('/auth/')) auth.sessionExpired();
      return throwError(() => err);
    }),
  );
};
