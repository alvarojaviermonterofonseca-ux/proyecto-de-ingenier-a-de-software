import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, of, tap } from 'rxjs';

import { ApiClient } from '../api/api-client.service';
import type { Permission } from '../api/api.models';
import {
  ACTIONS,
  RESOURCE_DEFINITIONS,
  actionLabel,
  resourceLabel,
} from './permissions';

export interface CatalogGroup {
  recurso: string;
  label: string;
  permissions: Permission[];
}

/**
 * Catálogo de permisos resuelto contra la API. La matriz de roles se construye
 * desde aquí y no desde la lista fija, para que un permiso nuevo creado por un
 * administrador aparezca sin recompilar el frontend.
 */
@Injectable({ providedIn: 'root' })
export class PermissionCatalogService {
  private readonly api = inject(ApiClient);

  private readonly _permissions = signal<Permission[]>([]);
  private readonly _loading = signal(false);
  private readonly _error = signal<string | null>(null);
  private inFlight: Observable<Permission[]> | null = null;

  readonly actions = ACTIONS;
  readonly permissions = this._permissions.asReadonly();
  readonly loading = this._loading.asReadonly();
  readonly error = this._error.asReadonly();
  readonly loaded = computed(() => this._permissions().length > 0);

  readonly groups = computed<CatalogGroup[]>(() =>
    this.groupPermissions(this._permissions().filter((permission) => permission.is_active)),
  );

  readonly resources = computed(() => {
    const known: string[] = RESOURCE_DEFINITIONS.map((definition) => definition.code);
    const extra = this._permissions()
      .map((permission) => permission.recurso)
      .filter((recurso) => !known.includes(recurso));
    return [...known, ...new Set(extra)];
  });

  load(force = false): Observable<Permission[]> {
    if (!force && this.loaded()) {
      return of(this._permissions());
    }
    if (!force && this.inFlight) {
      return this.inFlight;
    }
    this._loading.set(true);
    this._error.set(null);
    this.inFlight = this.api.getAll<Permission>('permisos/').pipe(
      tap({
        next: (permissions) => {
          this._permissions.set(permissions);
          this._loading.set(false);
          this.inFlight = null;
        },
        error: () => {
          this._permissions.set([]);
          this._error.set('No se pudo cargar el catálogo de permisos.');
          this._loading.set(false);
          this.inFlight = null;
        },
      }),
    );
    return this.inFlight;
  }

  /** Agrupa permisos arbitrarios; tolera recursos que no están en la lista fija. */
  groupPermissions(permissions: readonly Permission[]): CatalogGroup[] {
    const byResource = new Map<string, Permission[]>();
    for (const permission of permissions) {
      const current = byResource.get(permission.recurso) ?? [];
      current.push(permission);
      byResource.set(permission.recurso, current);
    }
    const order: string[] = RESOURCE_DEFINITIONS.map((definition) => definition.code);
    const actions: readonly string[] = ACTIONS;
    return [...byResource.entries()]
      .sort(([a], [b]) => {
        const positionA = order.indexOf(a);
        const positionB = order.indexOf(b);
        if (positionA === -1 && positionB === -1) return a.localeCompare(b);
        if (positionA === -1) return 1;
        if (positionB === -1) return -1;
        return positionA - positionB;
      })
      .map(([recurso, items]) => ({
        recurso,
        label: resourceLabel(recurso),
        permissions: [...items].sort(
          (a, b) => actions.indexOf(a.accion) - actions.indexOf(b.accion),
        ),
      }));
  }

  labelFor(resource: string): string {
    return resourceLabel(resource);
  }

  actionLabel(action: string): string {
    return actionLabel(action);
  }

  /** Convierte códigos sueltos (`recurso:accion`) en un catálogo mínimo. */
  static fromCodes(codes: readonly string[]): Permission[] {
    return codes.map((code, index) => {
      const [recurso, accion] = code.split(':');
      return {
        id: index,
        codigo: code,
        recurso: recurso ?? code,
        accion: accion ?? '',
        descripcion: null,
        is_active: true,
        created_at: '',
        updated_at: '',
      };
    });
  }
}
