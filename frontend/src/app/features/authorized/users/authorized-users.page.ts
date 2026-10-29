import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { ApiClient } from '../../../core/api/api-client.service';
import { ApiError } from '../../../core/api/api-error';
import type { PaginatedResponse, Role, UserDetail, UserSummary } from '../../../core/api/api.models';
import { AuthService } from '../../../core/auth/auth.service';
import { roleLabel } from '../../../core/rbac/permissions';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ToastService } from '../../../core/ui/toast.service';
import { formatDate } from '../../../core/utils/format';
import { AvatarComponent } from '../../../shared/avatar.component';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import { PaginationComponent } from '../../../shared/pagination.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';

type Editor = 'create' | 'identity' | 'roles' | null;

@Component({
  selector: 'app-authorized-users',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    AvatarComponent,
    EmptyStateComponent,
    IconComponent,
    ModalComponent,
    PageHeaderComponent,
    PaginationComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './authorized-users.page.html',
  styleUrl: './authorized-users.page.css',
})
export class AuthorizedUsersPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);

  protected readonly users = signal<UserSummary[]>([]);
  protected readonly roles = signal<Role[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 25;
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly selectedId = signal<number | null>(null);
  protected readonly detail = signal<UserDetail | null>(null);
  protected readonly detailLoading = signal(false);

  protected readonly editor = signal<Editor>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly roleDraft = signal<ReadonlySet<number>>(new Set());

  protected readonly search = this.formBuilder.nonNullable.control('');
  protected readonly roleFilter = this.formBuilder.nonNullable.control<number | ''>('');
  protected readonly includeInactive = this.formBuilder.nonNullable.control(false);

  protected readonly createForm = this.formBuilder.nonNullable.group({
    rol: [0, [Validators.required]],
    nombre: ['', [Validators.required, Validators.maxLength(150)]],
    username: [''],
    correo: ['', [Validators.required, Validators.email]],
    contrasena: ['', [Validators.required, Validators.minLength(8)]],
    telefono: [''],
    is_active: [true],
    tipo_documento: [''],
    numero_documento: [''],
    fecha_nacimiento: [''],
    objetivo: [''],
    peso_kg: [''],
    estatura_cm: [''],
    especialidad: [''],
    certificacion: [''],
    licencia_profesional: [''],
    biografia: [''],
    cargo: [''],
    nivel_permisos: ['operativo'],
    fecha_ingreso: [''],
    turno_preferido: [''],
  });

  protected readonly identityForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, Validators.maxLength(150)]],
    username: [''],
    correo: ['', [Validators.required, Validators.email]],
    telefono: [''],
    is_active: [true],
    contrasena: ['', [Validators.pattern(/^$|^.{8,}$/)]],
  });

  protected readonly activeRoles = computed(() => this.roles().filter((role) => role.is_active));

  protected readonly profileRole = computed(() => {
    const id = this.createForm.controls.rol.value;
    return this.roles().find((role) => role.id === id)?.nombre ?? '';
  });

  protected readonly additionalRoles = computed(() => {
    const detail = this.detail();
    if (!detail) return [];
    return (detail.roles_detalle ?? []).filter((role) => role.id !== detail.rol);
  });

  protected readonly canEdit = computed(() => this.auth.hasPermission('usuarios:edit'));
  protected readonly canDelete = computed(() => this.auth.hasPermission('usuarios:delete'));

  ngOnInit(): void {
    this.loadRoles();
    this.load();
    this.search.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.page.set(1);
        this.load();
      });
    this.roleFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.page.set(1);
      this.load();
    });
    this.includeInactive.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.page.set(1);
      this.load();
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .get<PaginatedResponse<UserSummary>>('usuarios/', {
        page: this.page(),
        search: this.search.value.trim(),
        rol: this.roleFilter.value || null,
        incluir_eliminados: this.includeInactive.value ? 1 : null,
      })
      .subscribe({
        next: (response) => {
          this.users.set(response.results);
          this.count.set(response.count);
          this.loading.set(false);
          if (this.selectedId() && !response.results.some((user) => user.id === this.selectedId())) {
            this.select(response.results[0] ?? null);
          } else if (!this.selectedId() && response.results.length > 0) {
            this.select(response.results[0]);
          }
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(
            error instanceof ApiError ? error.message : 'No se pudieron cargar los usuarios.',
          );
        },
      });
  }

  protected changePage(page: number): void {
    this.page.set(page);
    this.load();
  }

  protected select(user: UserSummary | null): void {
    if (!user) {
      this.selectedId.set(null);
      this.detail.set(null);
      return;
    }
    this.selectedId.set(user.id);
    this.loadDetail(user.id);
  }

  protected loadDetail(id: number): void {
    this.detailLoading.set(true);
    this.api.get<UserDetail>(`usuarios/${id}/`).subscribe({
      next: (detail) => {
        this.detail.set(detail);
        this.detailLoading.set(false);
      },
      error: (error: unknown) => {
        this.detailLoading.set(false);
        this.toast.error(
          'No se pudo abrir la ficha',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected statusOf(user: { is_active: boolean }): string {
    return user.is_active ? 'Activo' : 'Inactivo';
  }

  protected toneOf(user: { is_active: boolean }): 'success' | 'neutral' {
    return user.is_active ? 'success' : 'neutral';
  }

  protected roleName(id: number): string {
    return roleLabel(this.roles().find((role) => role.id === id)?.nombre ?? '');
  }

  protected openCreate(): void {
    this.formError.set(null);
    this.createForm.reset({
      rol: this.activeRoles()[0]?.id ?? 0,
      nombre: '',
      username: '',
      correo: '',
      contrasena: '',
      telefono: '',
      is_active: true,
      tipo_documento: '',
      numero_documento: '',
      fecha_nacimiento: '',
      objetivo: '',
      peso_kg: '',
      estatura_cm: '',
      especialidad: '',
      certificacion: '',
      licencia_profesional: '',
      biografia: '',
      cargo: '',
      nivel_permisos: 'operativo',
      fecha_ingreso: '',
      turno_preferido: '',
    });
    this.editor.set('create');
  }

  protected openIdentity(): void {
    const detail = this.detail();
    if (!detail) return;
    this.formError.set(null);
    this.identityForm.reset({
      nombre: detail.nombre,
      username: detail.username ?? '',
      correo: detail.correo,
      telefono: detail.telefono ?? '',
      is_active: detail.is_active,
      contrasena: '',
    });
    this.editor.set('identity');
  }

  protected openRoles(): void {
    const detail = this.detail();
    if (!detail) return;
    this.formError.set(null);
    this.roleDraft.set(
      new Set(
        (detail.roles_detalle ?? [])
          .filter((role) => role.id !== detail.rol)
          .map((role) => role.id),
      ),
    );
    this.editor.set('roles');
  }

  protected closeEditor(): void {
    if (!this.saving()) {
      this.editor.set(null);
    }
  }

  protected saveCreate(): void {
    this.formError.set(null);
    if (this.createForm.invalid) {
      this.createForm.markAllAsTouched();
      return;
    }
    const raw = this.createForm.getRawValue();
    const payload: Record<string, unknown> = {
      rol: raw.rol,
      nombre: raw.nombre.trim(),
      correo: raw.correo.trim(),
      contrasena: raw.contrasena,
      is_active: raw.is_active,
      perfil: this.buildProfile(raw.rol, raw),
    };
    if (raw.username.trim()) payload['username'] = raw.username.trim();
    if (raw.telefono.trim()) payload['telefono'] = raw.telefono.trim();

    this.saving.set(true);
    this.api.post<UserDetail>('usuarios/', payload).subscribe({
      next: (user) => {
        this.saving.set(false);
        this.editor.set(null);
        this.toast.success('Usuario creado', `${user.nombre} ya puede iniciar sesión.`);
        this.load();
        this.select({
          id: user.id,
          rol: user.rol,
          rol_nombre: user.rol_detalle?.nombre ?? '',
          roles_efectivos: [],
          nombre: user.nombre,
          username: user.username,
          correo: user.correo,
          telefono: user.telefono,
          is_active: user.is_active,
          perfil_detalle: user.perfil_detalle,
        });
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(this.errorMessage(error, 'No se pudo crear el usuario.'));
      },
    });
  }

  protected saveIdentity(): void {
    const detail = this.detail();
    if (!detail) return;
    this.formError.set(null);
    if (this.identityForm.invalid) {
      this.identityForm.markAllAsTouched();
      return;
    }
    const raw = this.identityForm.getRawValue();
    const payload: Record<string, unknown> = {
      nombre: raw.nombre.trim(),
      correo: raw.correo.trim(),
      is_active: raw.is_active,
    };
    if (raw.username.trim()) payload['username'] = raw.username.trim();
    if (raw.telefono.trim()) payload['telefono'] = raw.telefono.trim();
    if (raw.contrasena.trim()) payload['contrasena'] = raw.contrasena;

    this.saving.set(true);
    this.api.patch<UserDetail>(`usuarios/${detail.id}/`, payload).subscribe({
      next: (user) => {
        this.saving.set(false);
        this.editor.set(null);
        this.detail.set(user);
        this.toast.success('Usuario actualizado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(this.errorMessage(error, 'No se pudo guardar el usuario.'));
      },
    });
  }

  protected saveRoles(): void {
    const detail = this.detail();
    if (!detail) return;
    this.saving.set(true);
    this.formError.set(null);
    this.api
      .patch<UserDetail>(`usuarios/${detail.id}/roles/`, { roles: [...this.roleDraft()] })
      .subscribe({
        next: (user) => {
          this.saving.set(false);
          this.editor.set(null);
          this.detail.set(user);
          this.toast.success('Roles actualizados', 'Las sesiones del usuario se renovaron.');
          this.load();
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(this.errorMessage(error, 'No se pudieron asignar los roles.'));
        },
      });
  }

  protected toggleRole(roleId: number, checked: boolean): void {
    this.roleDraft.update((current) => {
      const next = new Set(current);
      if (checked) next.add(roleId);
      else next.delete(roleId);
      return next;
    });
  }

  protected isRoleSelected(roleId: number): boolean {
    return this.roleDraft().has(roleId);
  }

  protected async toggleActive(): Promise<void> {
    const detail = this.detail();
    if (!detail) return;
    const activating = !detail.is_active;
    if (!activating) {
      const accepted = await this.confirm.confirm({
        title: 'Desactivar usuario',
        message: `Se cerrarán las sesiones de ${detail.nombre} y no podrá iniciar sesión hasta reactivarlo.`,
        confirmLabel: 'Desactivar',
        tone: 'danger',
      });
      if (!accepted) return;
    }
    this.api.patch<UserDetail>(`usuarios/${detail.id}/`, { is_active: activating }).subscribe({
      next: (user) => {
        this.detail.set(user);
        this.toast.success(activating ? 'Usuario reactivado' : 'Usuario desactivado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudo cambiar el estado',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected async remove(): Promise<void> {
    const detail = this.detail();
    if (!detail) return;
    const accepted = await this.confirm.confirm({
      title: 'Eliminar usuario',
      message: `${detail.nombre} se ocultará del sistema. Un administrador puede restaurarlo desde esta misma ficha.`,
      confirmLabel: 'Eliminar',
      tone: 'danger',
    });
    if (!accepted) return;
    this.api.delete(`usuarios/${detail.id}/`).subscribe({
      next: () => {
        this.toast.success('Usuario eliminado');
        this.selectedId.set(null);
        this.detail.set(null);
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

  protected restore(): void {
    const detail = this.detail();
    if (!detail) return;
    this.api.post<UserDetail>(`usuarios/${detail.id}/restaurar/`, {}).subscribe({
      next: (user) => {
        this.detail.set(user);
        this.toast.success('Usuario restaurado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudo restaurar',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected createdAt(): string {
    return formatDate(this.detail()?.created_at);
  }

  protected roleLabel = roleLabel;

  private loadRoles(): void {
    this.api.getAll<Role>('roles/', { is_active: true }).subscribe({
      next: (roles) => {
        this.roles.set(roles);
        if (!this.createForm.controls.rol.value && roles.length > 0) {
          this.createForm.controls.rol.setValue(roles[0].id);
        }
      },
      error: () => this.roles.set([]),
    });
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (error instanceof ApiError) {
      const fields = error.fieldErrors();
      return Object.values(fields)[0] ?? error.message;
    }
    return fallback;
  }

  private buildProfile(roleId: number, raw: Record<string, unknown>): Record<string, unknown> {
    const role = this.roles().find((item) => item.id === roleId)?.nombre ?? '';
    const profile: Record<string, unknown> = {};
    const values: Record<string, string> = {
      tipo_documento: String(raw['tipo_documento'] ?? '').trim(),
      numero_documento: String(raw['numero_documento'] ?? '').trim(),
      fecha_nacimiento: String(raw['fecha_nacimiento'] ?? '').trim(),
      objetivo: String(raw['objetivo'] ?? '').trim(),
      peso_kg: String(raw['peso_kg'] ?? '').trim(),
      estatura_cm: String(raw['estatura_cm'] ?? '').trim(),
      especialidad: String(raw['especialidad'] ?? '').trim(),
      certificacion: String(raw['certificacion'] ?? '').trim(),
      licencia_profesional: String(raw['licencia_profesional'] ?? '').trim(),
      biografia: String(raw['biografia'] ?? '').trim(),
      cargo: String(raw['cargo'] ?? '').trim(),
      nivel_permisos: String(raw['nivel_permisos'] ?? '').trim(),
      fecha_ingreso: String(raw['fecha_ingreso'] ?? '').trim(),
      turno_preferido: String(raw['turno_preferido'] ?? '').trim(),
    };
    const fieldsByRole: Record<string, string[]> = {
      cliente: [
        'tipo_documento',
        'numero_documento',
        'fecha_nacimiento',
        'objetivo',
        'peso_kg',
        'estatura_cm',
      ],
      entrenador: ['especialidad', 'certificacion', 'fecha_ingreso', 'biografia'],
      terapeuta: ['especialidad', 'licencia_profesional', 'fecha_ingreso'],
      recepcionista: ['fecha_ingreso', 'turno_preferido'],
      administrador: ['cargo', 'fecha_ingreso', 'nivel_permisos'],
    };
    for (const field of fieldsByRole[role] ?? []) {
      if (values[field]) {
        profile[field] = values[field];
      }
    }
    return profile;
  }
}
