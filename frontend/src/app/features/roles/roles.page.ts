import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { of, switchMap } from 'rxjs';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Permission, Role } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { groupPermissions, type PermissionGroup } from '../../core/rbac/permissions';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-roles-page',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    IconComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './roles.page.html',
  styleUrl: './roles.page.css',
})
export class RolesPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly roles = signal<Role[]>([]);
  protected readonly permissions = signal<Permission[]>([]);
  protected readonly selected = signal<ReadonlySet<string>>(new Set());
  protected readonly permissionQuery = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<Role | null>(null);

  protected readonly form = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, Validators.maxLength(50)]],
    descripcion: [''],
    is_active: [true],
  });

  protected readonly groups = computed<PermissionGroup[]>(() => {
    const query = this.permissionQuery().trim().toLowerCase();
    const all = groupPermissions(this.permissions());
    if (!query) return all;
    return all
      .map((group) => ({
        ...group,
        permissions: group.permissions.filter(
          (permission) =>
            permission.codigo.toLowerCase().includes(query) ||
            (permission.descripcion ?? '').toLowerCase().includes(query),
        ),
      }))
      .filter((group) => group.permissions.length > 0);
  });

  protected readonly canEditPermissions = computed(
    () => this.auth.isAdmin() && this.auth.hasPermission('roles:edit'),
  );

  protected readonly totalPermissions = computed(() => this.permissions().length);

  ngOnInit(): void {
    this.load();
    this.api.getAll<Permission>('permisos/', { is_active: true }).subscribe({
      next: (permissions) => this.permissions.set(permissions),
      error: () => this.permissions.set([]),
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Role>('roles/').subscribe({
      next: (roles) => {
        this.roles.set(roles);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los roles.');
      },
    });
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.selected.set(new Set());
    this.form.reset({ nombre: '', descripcion: '', is_active: true });
    this.form.controls.nombre.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(role: Role): void {
    this.editing.set(role);
    this.formError.set(null);
    this.selected.set(new Set(role.permisos));
    this.form.reset({
      nombre: role.nombre,
      descripcion: role.descripcion ?? '',
      is_active: role.is_active,
    });
    if (role.total_usuarios > 0) {
      this.form.controls.nombre.disable();
    } else {
      this.form.controls.nombre.enable();
    }
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.modalOpen.set(false);
    }
  }

  protected save(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const editing = this.editing();
    const payload = {
      nombre: raw.nombre.trim(),
      descripcion: raw.descripcion.trim() || null,
      is_active: raw.is_active,
    };
    this.saving.set(true);
    const request = editing
      ? this.api.patch<Role>(`roles/${editing.id}/`, payload)
      : this.api.post<Role>('roles/', payload);

    request
      .pipe(
        switchMap((role) =>
          this.canEditPermissions()
            ? this.api.put(`roles/${role.id}/permisos/`, {
                permisos: [...this.selected()],
              })
            : of(null),
        ),
      )
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.modalOpen.set(false);
          this.toast.success(editing ? 'Rol actualizado' : 'Rol creado');
          this.load();
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(
            error instanceof ApiError ? error.message : 'No se pudo guardar el rol.',
          );
        },
      });
  }

  protected togglePermission(code: string, checked: boolean): void {
    this.selected.update((current) => {
      const next = new Set(current);
      if (checked) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  protected toggleGroup(group: PermissionGroup, checked: boolean): void {
    this.selected.update((current) => {
      const next = new Set(current);
      for (const permission of group.permissions) {
        if (checked) next.add(permission.codigo);
        else next.delete(permission.codigo);
      }
      return next;
    });
  }

  protected groupSelected(group: PermissionGroup): boolean {
    return (
      group.permissions.length > 0 &&
      group.permissions.every((permission) => this.selected().has(permission.codigo))
    );
  }

  protected isSelected(code: string): boolean {
    return this.selected().has(code);
  }

  protected permissionCountLabel(role: Role): string {
    return `${role.permisos.length} permisos`;
  }

  protected async remove(role: Role): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar rol',
      message: `Se desactivará el rol ${role.nombre}. Los usuarios que lo tengan asignado perderán sus accesos.`,
      confirmLabel: 'Eliminar rol',
    });
    if (!accepted) return;
    this.api.delete(`roles/${role.id}/`).subscribe({
      next: () => {
        this.toast.success('Rol eliminado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected updatePermissionQuery(value: string): void {
    this.permissionQuery.set(value);
  }
}
