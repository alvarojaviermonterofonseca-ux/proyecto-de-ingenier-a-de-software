import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../auth/auth.service';

export const permissionGuard: CanActivateFn = async (route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!(await auth.restore())) {
    return router.createUrlTree(['/login'], {
      queryParams: { returnUrl: state.url },
    });
  }

  if (route.data['adminOnly'] === true && !auth.isAdmin()) {
    return router.createUrlTree(['/acceso-denegado'], {
      queryParams: { returnUrl: state.url },
    });
  }

  const required = route.data['permission'] as string | string[] | undefined;
  if (!required) {
    return true;
  }
  const allowed = Array.isArray(required)
    ? auth.hasAny(required)
    : auth.hasPermission(required);
  if (allowed) {
    return true;
  }
  return router.createUrlTree(['/acceso-denegado'], {
    queryParams: { returnUrl: state.url },
  });
};
