import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { apiUrl } from './api-config';
import { AuthService } from './auth.service';

/** Adds "Authorization: Bearer <token>" to API calls and logs out on 401 (expired token). */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.token;
  if (!req.url.startsWith(apiUrl())) return next(req);
  const headers: Record<string, string> = {
    // Lets API calls pass through an ngrok tunnel without its browser warning page.
    'ngrok-skip-browser-warning': 'true',
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const authReq = req.clone({ setHeaders: headers });
  return next(authReq).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status === 401 && token) auth.logout();
      return throwError(() => err);
    }),
  );
};
