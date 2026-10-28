import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { TokenStorage } from './token-storage.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const tokens = inject(TokenStorage);
  const token = tokens.token;
  if (!token || request.url.endsWith('/login/')) {
    return next(request);
  }
  return next(
    request.clone({
      setHeaders: { Authorization: `Bearer ${token}` },
    }),
  );
};
