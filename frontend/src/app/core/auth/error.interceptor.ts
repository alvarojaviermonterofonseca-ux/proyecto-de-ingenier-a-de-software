import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { ApiError } from '../api/api-error';
import { TokenStorage } from './token-storage.service';

export const errorInterceptor: HttpInterceptorFn = (request, next) => {
  const tokens = inject(TokenStorage);
  const router = inject(Router);

  return next(request).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse)) {
        return throwError(() => error);
      }

      const apiError = ApiError.from(error.status, error.error);
      const isLogin = request.url.endsWith('/login/');
      if (error.status === 401 && !isLogin) {
        tokens.clear();
        tokens.notifyExpired();
        const current = router.url;
        if (!current.startsWith('/login')) {
          void router.navigate(['/login'], {
            queryParams: { expired: '1', returnUrl: current },
          });
        }
      }
      return throwError(() => apiError);
    }),
  );
};
