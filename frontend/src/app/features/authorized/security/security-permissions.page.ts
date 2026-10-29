import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../../core/api/api-client.service';
import { ApiError } from '../../../core/api/api-error';
import type { Permission, Role } from '../../../core/api/api.models';
import { AuthService } from '../../../core/auth/auth.service';
import {
  PermissionCatalogService,
  type CatalogGroup,
} from '../../../core/rbac/permission-catalog.service';
import { ACTIONS, actionLabel } from '../../../core/rbac/permissions';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';

@Component({
  selector: 'app-security-permissions',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    EmptyStateComponent,
    IconComponent,
    ModalComponent,
    PageHeaderComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './security-permissions.page.html',
  styleUrl: './security-permissions.page.css',
})
export class SecurityPermissionsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly catalog = inject(PermissionCatalogService);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);
  protected readonly auth = inject(AuthService);

  protected readonly actions = ACTIONS;
  protected readonly actionLabel = actionLabel;

  protected readonly roles = signal<Role[]>([]);
  protected readonly items = signal<Permission[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly query = signal('');
  protected readonly resourceFilter = signal('');
  protected readonly editor = signal<'create' | 'edit' | null>(null);
  protected readonly editing = signal<Permission | null>(null);

  protected readonly canCreate = computed(() => this.auth.hasPermission('permisos:create'));
  protected readonly canEdit = computed(() => this.auth.hasPermission('permisos:edit'));
  protected readonly canDelete = computed(() => this.auth.hasPermission('permisos:delete'));

  protected readonly form = this.formBuilder.nonNullable.group({
    recurso: ['', [Validators.required, Validators.pattern(/^[a-z0-9-]+$/)]],
    accion: ['view', [Validators.required]],
    descripcion: [''],
    is_active: [true],
  });

  protected readonly resources = computed(() => {
    const known = this.catalog.resources();
    const used = this.items().map((permission) => permission.recurso);
    return [...new Set([...known, ...used])];
  });

  protected readonly groups = computed<CatalogGroup[]>(() => {
    const query = this.query().trim().toLowerCase();
    const resource = this.resourceFilter();
    return this.catalog
      .groupPermissions(this.items())
      .map((group) => ({
        ...group,
        permissions: group.permissions.filter((permission) => {
          if (resource && permission.recurso !== resource) return false;
          if (!query) return true;
          return (
            permission.codigo.toLowerCase().includes(query) ||
            (permission.descripcion ?? '').toLowerCase().includes(query) ||
            group.label.toLowerCase().includes(query)
          );
        }),
      }))
      .filter((group) => group.permissions.length > 0);
  });

  protected readonly visibleCount = computed(() =>
    this.groups().reduce((total, group) => total + group.permissions.length, 0),
  );

  protected readonly usage = computed(() => {
    const counters = new Map<string, number>();
    for (const role of this.roles()) {
      for (const code of role.permisos) {
        counters.set(code, (counters.get(code) ?? 0) + 1);
      }
    }
    return counters;
  });

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Permission>('permisos/', { incluir_eliminados: 1 }).subscribe({
      next: (items) => {
        this.items.set(items);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof ApiError
            ? error.message
            : 'No se pudo cargar el catálogo de permisos.',
        );
      },
    });
    this.catalog.load(true).subscribe();
    this.api.getAll<Role>('roles/').subscribe({
      next: (roles) => this.roles.set(roles),
      error: () => this.roles.set([]),
    });
  }

  protected usageOf(code: string): number {
    return this.usage().get(code) ?? 0;
  }

  protected updateQuery(value: string): void {
    this.query.set(value);
  }

  protected updateResource(value: string): void {
    this.resourceFilter.set(value);
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({ recurso: '', accion: 'view', descripcion: '', is_active: true });
    this.form.controls.recurso.enable();
    this.form.controls.accion.enable();
    this.editor.set('create');
  }

  protected openEdit(permission: Permission): void {
    this.editing.set(permission);
    this.formError.set(null);
    this.form.reset({
      recurso: permission.recurso,
      accion: permission.accion,
      descripcion: permission.descripcion ?? '',
      is_active: permission.is_active,
    });
    this.form.controls.recurso.disable();
    this.form.controls.accion.disable();
    this.editor.set('edit');
  }

  protected closeEditor(): void {
    if (!this.saving()) this.editor.set(null);
  }

  protected save(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const editing = this.editing();
    this.saving.set(true);

    const request = editing
      ? this.api.patch<Permission>(`permisos/${editing.id}/`, {
          descripcion: raw.descripcion.trim() || null,
          is_active: raw.is_active,
        })
      : this.api.post<Permission>('permisos/', {
          recurso: raw.recurso.trim(),
          accion: raw.accion,
          descripcion: raw.descripcion.trim() || null,
        });

    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.editor.set(null);
        this.toast.success(editing ? 'Permiso actualizado' : 'Permiso creado');
        this.reload();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(
          error instanceof ApiError ? error.message : 'No se pudo guardar el permiso.',
        );
      },
    });
  }

  protected async remove(permission: Permission): Promise<void> {
    const usage = this.usageOf(permission.codigo);
    const accepted = await this.confirm.confirm({
      title: 'Eliminar permiso',
      message:
        usage > 0
          ? `${permission.codigo} está asignado a ${usage} rol(es). Se desactivará y esos roles perderán el acceso.`
          : `Se desactivará ${permission.codigo} y dejará de aparecer en la matriz de roles.`,
      confirmLabel: 'Eliminar permiso',
      tone: 'danger',
    });
    if (!accepted) return;
    this.api.delete(`permisos/${permission.id}/`).subscribe({
      next: () => {
        this.toast.success('Permiso eliminado');
        this.reload();
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudo eliminar',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected toggleActive(permission: Permission): void {
    this.api
      .patch<Permission>(`permisos/${permission.id}/`, { is_active: !permission.is_active })
      .subscribe({
        next: () => {
          this.toast.success(permission.is_active ? 'Permiso desactivado' : 'Permiso activado');
          this.reload();
        },
        error: (error: unknown) => {
          this.toast.error(
            'No se pudo cambiar el estado',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
  }

  private reload(): void {
    this.catalog.load(true).subscribe();
    this.api.getAll<Permission>('permisos/', { incluir_eliminados: 1 }).subscribe({
      next: (items) => this.items.set(items),
      error: () => undefined,
    });
  }
}
