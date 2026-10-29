import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../../core/api/api-client.service';
import { ApiError } from '../../../core/api/api-error';
import type {
  Role,
  UserRoleAssignment,
  UserSummary,
} from '../../../core/api/api.models';
import { roleLabel } from '../../../core/rbac/permissions';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ToastService } from '../../../core/ui/toast.service';
import { formatDate } from '../../../core/utils/format';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { ModalComponent } from '../../../shared/modal.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';

@Component({
  selector: 'app-security-assignments',
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
  templateUrl: './security-assignments.page.html',
  styleUrl: './security-assignments.page.css',
})
export class SecurityAssignmentsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly assignments = signal<UserRoleAssignment[]>([]);
  protected readonly users = signal<UserSummary[]>([]);
  protected readonly roles = signal<Role[]>([]);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly editor = signal(false);
  protected readonly roleLabel = roleLabel;
  protected readonly formatDate = formatDate;

  protected readonly filter = this.formBuilder.nonNullable.group({
    usuario: [''],
    rol: [0],
    activo: [''],
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    usuario: [0, [Validators.required, Validators.min(1)]],
    rol: [0, [Validators.required, Validators.min(1)]],
  });

  protected readonly visible = computed(() => {
    const { usuario, rol, activo } = this.filter.getRawValue();
    const query = usuario.trim().toLowerCase();
    return this.assignments().filter((item) => {
      if (query) {
        const haystack = `${item.usuario_nombre} ${item.rol_nombre}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      if (rol && item.rol !== rol) return false;
      if (activo === 'activos' && !item.activo) return false;
      if (activo === 'inactivos' && item.activo) return false;
      return true;
    });
  });

  protected readonly activeCount = computed(
    () => this.assignments().filter((item) => item.activo).length,
  );

  protected isPrincipal(item: UserRoleAssignment): boolean {
    const user = this.users().find((candidate) => candidate.id === item.usuario);
    return user?.rol === item.rol;
  }

  ngOnInit(): void {
    this.load();
    this.loadOptions();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<UserRoleAssignment>('usuarios-roles/').subscribe({
      next: (items) => {
        this.assignments.set(items);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof ApiError
            ? error.message
            : 'No se pudieron cargar las asignaciones.',
        );
      },
    });
  }

  protected openCreate(): void {
    this.formError.set(null);
    this.form.reset({
      usuario: this.users()[0]?.id ?? 0,
      rol: this.roles()[0]?.id ?? 0,
    });
    this.editor.set(true);
  }

  protected closeEditor(): void {
    if (!this.saving()) this.editor.set(false);
  }

  protected create(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    this.saving.set(true);
    this.api
      .post<UserRoleAssignment>('usuarios-roles/', { usuario: raw.usuario, rol: raw.rol })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.editor.set(false);
          this.toast.success('Rol asignado', 'Las sesiones del usuario se renovaron.');
          this.load();
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(
            error instanceof ApiError
              ? this.firstFieldError(error)
              : 'No se pudo asignar el rol.',
          );
        },
      });
  }

  protected toggleActive(item: UserRoleAssignment): void {
    this.api
      .patch<UserRoleAssignment>(`usuarios-roles/${item.id}/`, { activo: !item.activo })
      .subscribe({
        next: (updated) => {
          this.assignments.update((items) =>
            items.map((current) => (current.id === updated.id ? updated : current)),
          );
          this.toast.success(
            updated.activo ? 'Asignación reactivada' : 'Asignación desactivada',
          );
        },
        error: (error: unknown) => {
          this.toast.error(
            'No se pudo cambiar la asignación',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
  }

  protected async remove(item: UserRoleAssignment): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Revocar rol',
      message: `${roleLabel(item.rol_nombre)} dejará de estar asignado a ${item.usuario_nombre}. La asignación se elimina del historial.`,
      confirmLabel: 'Revocar',
      tone: 'danger',
    });
    if (!accepted) return;
    this.api.delete(`usuarios-roles/${item.id}/`).subscribe({
      next: () => {
        this.toast.success('Rol revocado');
        this.assignments.update((items) => items.filter((current) => current.id !== item.id));
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudo revocar',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected clearFilters(): void {
    this.filter.reset({ usuario: '', rol: 0, activo: '' });
  }

  private loadOptions(): void {
    this.api.getAll<UserSummary>('usuarios/').subscribe({
      next: (users) => this.users.set(users),
      error: () => this.users.set([]),
    });
    this.api.getAll<Role>('roles/', { is_active: true }).subscribe({
      next: (roles) => this.roles.set(roles),
      error: () => this.roles.set([]),
    });
  }

  private firstFieldError(error: ApiError): string {
    const fields = error.fieldErrors();
    return Object.values(fields)[0] ?? error.message;
  }
}
