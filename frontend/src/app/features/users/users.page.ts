import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { PaginatedResponse, Role, UserDetail, UserSummary } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { roleLabel } from '../../core/rbac/permissions';
import { humanize } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-users-page',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    IconComponent,
    AvatarComponent,
    PageHeaderComponent,
    PaginationComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './users.page.html',
  styleUrl: './users.page.css',
})
export class UsersPage implements OnInit {
  private readonly api = inject(ApiClient);
  protected readonly auth = inject(AuthService);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly users = signal<UserSummary[]>([]);
  protected readonly roles = signal<Role[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 25;
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<UserSummary | null>(null);

  protected readonly search = this.formBuilder.nonNullable.control('');
  protected readonly roleFilter = this.formBuilder.nonNullable.control<number | ''>('');
  protected readonly activeFilter = this.formBuilder.nonNullable.control('');

  protected readonly form = this.formBuilder.nonNullable.group({
    rol: [0, [Validators.required]],
    nombre: ['', [Validators.required, Validators.maxLength(150)]],
    username: [''],
    correo: ['', [Validators.required, Validators.email]],
    contrasena: [''],
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
    this.activeFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
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
        is_active: this.activeFilter.value || null,
      })
      .subscribe({
        next: (response) => {
          this.users.set(response.results);
          this.count.set(response.count);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los usuarios.');
        },
      });
  }

  protected changePage(page: number): void {
    this.page.set(page);
    this.load();
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      rol: this.roles()[0]?.id ?? 0,
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
    this.form.controls.contrasena.setValidators([Validators.required, Validators.minLength(8)]);
    this.form.controls.contrasena.updateValueAndValidity();
    this.modalOpen.set(true);
  }

  protected openEdit(user: UserSummary): void {
    this.editing.set(user);
    this.formError.set(null);
    this.form.reset({
      rol: user.rol,
      nombre: user.nombre,
      username: user.username ?? '',
      correo: user.correo,
      contrasena: '',
      telefono: user.telefono ?? '',
      is_active: user.is_active,
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
    this.form.controls.contrasena.clearValidators();
    this.form.controls.contrasena.updateValueAndValidity();
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
    const payload: Record<string, unknown> = {
      rol: raw.rol,
      nombre: raw.nombre.trim(),
      correo: raw.correo.trim(),
      is_active: raw.is_active,
    };
    if (raw.username.trim()) payload['username'] = raw.username.trim();
    if (raw.telefono.trim()) payload['telefono'] = raw.telefono.trim();

    if (!editing) {
      payload['contrasena'] = raw.contrasena;
      const profile = this.buildProfile(raw.rol, raw);
      payload['perfil'] = profile;
    } else if (raw.contrasena) {
      payload['contrasena'] = raw.contrasena;
    }

    this.saving.set(true);
    const request = editing
      ? this.api.patch<UserDetail>(`usuarios/${editing.id}/`, payload)
      : this.api.post<UserDetail>('usuarios/', payload);

    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Usuario actualizado' : 'Usuario creado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        if (error instanceof ApiError) {
          const fields = error.fieldErrors();
          const first = Object.values(fields)[0];
          this.formError.set(first || error.message);
        } else {
          this.formError.set('No se pudo guardar el usuario.');
        }
      },
    });
  }

  protected async remove(user: UserSummary): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar usuario',
      message: `Se desactivará y ocultará la cuenta de ${user.nombre}. Esta acción se puede revertir por un administrador.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`usuarios/${user.id}/`).subscribe({
      next: () => {
        this.toast.success('Usuario eliminado');
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

  protected selectedRoleName(): string {
    const id = this.form.controls.rol.value;
    return this.roles().find((role) => role.id === id)?.nombre ?? '';
  }

  protected roleLabel = roleLabel;
  protected humanize = humanize;

  private loadRoles(): void {
    this.api.getAll<Role>('roles/', { is_active: true }).subscribe({
      next: (roles) => this.roles.set(roles),
      error: () => this.roles.set([]),
    });
  }

  private buildProfile(roleId: number, raw: Record<string, unknown>): Record<string, unknown> {
    const role = this.roles().find((item) => item.id === roleId)?.nombre;
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
      cliente: ['tipo_documento', 'numero_documento', 'fecha_nacimiento', 'objetivo', 'peso_kg', 'estatura_cm'],
      entrenador: ['especialidad', 'certificacion', 'fecha_ingreso', 'biografia'],
      terapeuta: ['especialidad', 'licencia_profesional', 'fecha_ingreso'],
      recepcionista: ['fecha_ingreso', 'turno_preferido'],
      administrador: ['cargo', 'fecha_ingreso', 'nivel_permisos'],
    };
    for (const field of fieldsByRole[role ?? ''] ?? []) {
      if (values[field]) {
        profile[field] = values[field];
      }
    }
    return profile;
  }
}
