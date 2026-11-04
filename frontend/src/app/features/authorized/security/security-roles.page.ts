import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../../core/api/api-client.service';
import { ApiError } from '../../../core/api/api-error';
import type { Role, UserDetail } from '../../../core/api/api.models';
import { AuthService } from '../../../core/auth/auth.service';
import {
  PermissionCatalogService,
  type CatalogGroup,
} from '../../../core/rbac/permission-catalog.service';
import { ACTIONS, actionLabel, roleLabel } from '../../../core/rbac/permissions';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';

@Component({
  selector: 'app-security-roles',
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
  templateUrl: './security-roles.page.html',
  styleUrl: './security-roles.page.css',
})
export class SecurityRolesPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly catalog = inject(PermissionCatalogService);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);
  protected readonly auth = inject(AuthService);

  protected readonly actions = ACTIONS;
  protected readonly actionLabel = actionLabel;
  protected readonly roleLabel = roleLabel;

  protected readonly roles = signal<Role[]>([]);
  protected readonly users = signal<UserDetail[]>([]);
  protected readonly selectedId = signal<number | null>(null);
  protected readonly draft = signal<ReadonlySet<string>>(new Set());
  protected readonly query = signal('');
  protected readonly onlyAssigned = signal(false);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly editor = signal<'create' | 'roles' | null>(null);

  protected readonly selectedUser = signal<UserDetail | null>(null);
  protected readonly roleDraft = signal<Set<number>>(new Set());

  protected readonly activeRoles = computed(() => this.roles().filter((role) => role.is_active));

  protected readonly canEditPermissions = computed(
    () => this.auth.isAdmin() || this.auth.hasPermission('roles:edit'),
  );
  protected readonly canCreate = computed(() => this.auth.isAdmin() || this.auth.hasPermission('roles:create'));
  protected readonly canDelete = computed(() => this.auth.isAdmin() || this.auth.hasPermission('roles:delete'));
  protected readonly canAssignRoles = computed(
    () => this.auth.isAdmin() || this.auth.hasPermission('roles:edit') || this.auth.hasPermission('usuarios:edit'),
  );

  protected readonly form = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, Validators.maxLength(50)]],
    descripcion: [''],
  });

  protected readonly selectedRole = computed(
    () => this.roles().find((role) => role.id === this.selectedId()) ?? null,
  );

  protected readonly catalogGroups = computed<CatalogGroup[]>(() =>
    this.catalog.groupPermissions(this.catalog.permissions().filter((permission) => permission.is_active)),
  );

  protected readonly visibleGroups = computed<CatalogGroup[]>(() => {
    const query = this.query().trim().toLowerCase();
    const selected = this.draft();
    return this.catalogGroups()
      .map((group) => ({
        ...group,
        permissions: group.permissions.filter((permission) => {
          if (!query) return true;
          return (
            permission.codigo.toLowerCase().includes(query) ||
            (permission.descripcion ?? '').toLowerCase().includes(query) ||
            group.label.toLowerCase().includes(query)
          );
        }),
      }))
      .filter((group) => group.permissions.length > 0)
      .filter((group) =>
        this.onlyAssigned()
          ? group.permissions.some((permission) => selected.has(permission.codigo))
          : true,
      );
  });

  protected readonly totalPermissions = computed(() => this.catalog.permissions().length);

  protected readonly dirty = computed(() => {
    const role = this.selectedRole();
    if (!role) return false;
    const current = [...this.draft()].sort().join('|');
    const saved = [...role.permisos].sort().join('|');
    return current !== saved;
  });

  protected readonly selectedCount = computed(() => this.draft().size);

  ngOnInit(): void {
    this.load(true);
    this.loadUsers();
    this.catalog.load().subscribe();
  }

  protected load(selectFirst = false): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Role>('roles/').subscribe({
      next: (roles) => {
        this.roles.set(roles);
        this.loading.set(false);
        const current = this.selectedId();
        if (current && !roles.some((role) => role.id === current)) {
          this.selectedId.set(null);
          this.draft.set(new Set());
        }
        if (selectFirst && !this.selectedId()) {
          this.select(roles[0] ?? null);
        }
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof ApiError ? error.message : 'No se pudieron cargar los roles.',
        );
      },
    });
  }

  protected loadUsers(): void {
    this.api.getAll<UserDetail>('usuarios/').subscribe({
      next: (users) => this.users.set(users),
      error: () => this.users.set([]),
    });
  }

  protected select(role: Role | null): void {
    if (!role) {
      this.selectedId.set(null);
      this.draft.set(new Set());
      return;
    }
    this.selectedId.set(role.id);
    this.draft.set(new Set(role.permisos));
    this.query.set('');
    this.onlyAssigned.set(false);
  }

  protected isChecked(code: string): boolean {
    return this.draft().has(code);
  }

  protected permissionFor(group: CatalogGroup, action: string) {
    return group.permissions.find((permission) => permission.accion === action);
  }

  protected togglePermission(code: string, checked: boolean): void {
    if (!this.canEditPermissions()) return;
    this.draft.update((current) => {
      const next = new Set(current);
      if (checked) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  protected groupState(group: CatalogGroup): 'all' | 'none' | 'partial' {
    const total = group.permissions.length;
    const selected = group.permissions.filter((permission) =>
      this.draft().has(permission.codigo),
    ).length;
    if (selected === 0) return 'none';
    if (selected === total) return 'all';
    return 'partial';
  }

  protected toggleGroup(group: CatalogGroup, checked: boolean): void {
    if (!this.canEditPermissions()) return;
    this.draft.update((current) => {
      const next = new Set(current);
      for (const permission of group.permissions) {
        if (checked) next.add(permission.codigo);
        else next.delete(permission.codigo);
      }
      return next;
    });
  }

  protected updateQuery(value: string): void {
    this.query.set(value);
  }

  protected toggleOnlyAssigned(checked: boolean): void {
    this.onlyAssigned.set(checked);
  }

  protected revert(): void {
    const role = this.selectedRole();
    if (role) {
      this.draft.set(new Set(role.permisos));
    }
  }

  protected save(): void {
    const role = this.selectedRole();
    if (!role) return;
    const permisos = [...this.draft()].sort();
    this.saving.set(true);
    this.api
      .put(`roles/${role.id}/permisos/`, { permisos })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.roles.update((roles) =>
            roles.map((item) => (item.id === role.id ? { ...item, permisos } : item)),
          );
          this.toast.success(
            'Permisos guardados',
            'El menú y los accesos se actualizan sin cerrar la sesión.',
          );
          this.auth.refresh().subscribe({ error: () => undefined });
          this.load();
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.toast.error(
            'No se pudieron guardar los permisos',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
  }

  protected openCreate(): void {
    this.formError.set(null);
    this.form.reset({ nombre: '', descripcion: '' });
    this.editor.set('create');
  }

  protected closeEditor(): void {
    if (!this.saving()) this.editor.set(null);
  }

  protected createRole(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    this.saving.set(true);
    this.api
      .post<Role>('roles/', {
        nombre: raw.nombre.trim().toLowerCase(),
        descripcion: raw.descripcion.trim() || null,
      })
      .subscribe({
        next: (role) => {
          this.saving.set(false);
          this.editor.set(null);
          this.toast.success('Rol creado', 'Asígnale permisos para que sea útil.');
          this.load();
          this.select(role);
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(
            error instanceof ApiError ? error.message : 'No se pudo crear el rol.',
          );
        },
      });
  }

  protected async remove(role: Role): Promise<void> {
    if (role.nombre === 'administrador') {
      this.toast.warning('Rol protegido', 'El rol administrador no se puede eliminar.');
      return;
    }
    const accepted = await this.confirm.confirm({
      title: 'Eliminar rol',
      message: `Se desactivará ${roleLabel(role.nombre)}. Los usuarios que lo tengan asignado perderán esos accesos.`,
      confirmLabel: 'Eliminar rol',
      tone: 'danger',
    });
    if (!accepted) return;
    this.api.delete(`roles/${role.id}/`).subscribe({
      next: () => {
        this.toast.success('Rol eliminado');
        this.selectedId.set(null);
        this.draft.set(new Set());
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudo eliminar',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected isProtected(role: Role): boolean {
    return role.nombre === 'administrador';
  }

  // --- Asignación de roles a usuarios ---

  protected openAssignRoles(user?: UserDetail): void {
    this.formError.set(null);
    if (user) {
      this.selectedUser.set(user);
      this.roleDraft.set(new Set((user.roles_detalle ?? []).map((r) => r.id)));
    } else {
      const first = this.users()[0] ?? null;
      this.selectedUser.set(first);
      this.roleDraft.set(first ? new Set((first.roles_detalle ?? []).map((r) => r.id)) : new Set());
    }
    this.editor.set('roles');
  }

  protected openAssignThisRole(role: Role): void {
    this.formError.set(null);
    const first = this.users()[0] ?? null;
    this.selectedUser.set(first);
    if (first) {
      const set = new Set((first.roles_detalle ?? []).map((r) => r.id));
      set.add(role.id);
      this.roleDraft.set(set);
    } else {
      this.roleDraft.set(new Set([role.id]));
    }
    this.editor.set('roles');
  }

  protected selectUserForAssignment(userIdStr: string): void {
    const id = Number(userIdStr);
    const user = this.users().find((u) => u.id === id) ?? null;
    this.selectedUser.set(user);
    if (user) {
      this.roleDraft.set(new Set((user.roles_detalle ?? []).map((r) => r.id)));
    } else {
      this.roleDraft.set(new Set());
    }
  }

  protected toggleRoleDraft(roleId: number, checked: boolean): void {
    this.roleDraft.update((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(roleId);
      } else {
        next.delete(roleId);
      }
      return next;
    });
  }

  protected isRoleDraftSelected(roleId: number): boolean {
    return this.roleDraft().has(roleId);
  }

  protected saveUserRoles(): void {
    const user = this.selectedUser();
    if (!user) return;

    this.saving.set(true);
    this.formError.set(null);
    const roleIds = [...this.roleDraft()];

    this.api
      .patch<UserDetail>(`usuarios/${user.id}/roles/`, { roles: roleIds })
      .subscribe({
        next: (updated) => {
          this.saving.set(false);
          this.editor.set(null);
          this.users.update((list) => list.map((u) => (u.id === updated.id ? updated : u)));
          this.load();
          this.toast.success(
            'Roles actualizados',
            `Se actualizaron los roles de ${user.nombre}. Las sesiones se renovaron.`,
          );
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(
            error instanceof ApiError ? error.message : 'No se pudieron asignar los roles.',
          );
        },
      });
  }
}
