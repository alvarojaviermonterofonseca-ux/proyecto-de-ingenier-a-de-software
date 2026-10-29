import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';
import {
  PermissionCatalogService,
  type CatalogGroup,
} from '../../core/rbac/permission-catalog.service';
import { actionLabel, roleLabel } from '../../core/rbac/permissions';
import { ToastService } from '../../core/ui/toast.service';
import { formatDate } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { IconComponent } from '../../shared/icon.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-my-access',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    AvatarComponent,
    IconComponent,
    PageHeaderComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './my-access.page.html',
  styleUrl: './my-access.page.css',
})
export class MyAccessPage {
  private readonly api = inject(ApiClient);
  private readonly catalog = inject(PermissionCatalogService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);
  protected readonly auth = inject(AuthService);

  protected readonly roleLabel = roleLabel;
  protected readonly actionLabel = actionLabel;

  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly fieldErrors = signal<Record<string, string>>({});

  protected readonly showPassword = signal(false);

  protected readonly form = this.formBuilder.nonNullable.group({
    contrasena_actual: ['', [Validators.required]],
    contrasena_nueva: ['', [Validators.required, Validators.minLength(8)]],
    confirmacion: ['', [Validators.required]],
  });

  protected readonly user = this.auth.user;

  protected readonly codes = computed(() => {
    const user = this.user();
    return [...new Set(user?.permisos_efectivos ?? user?.permisos ?? [])].sort();
  });

  protected readonly groups = computed<CatalogGroup[]>(() =>
    this.catalog.groupPermissions(PermissionCatalogService.fromCodes(this.codes())),
  );

  protected readonly roles = computed(() => {
    const user = this.user();
    if (!user) return [];
    const list = user.roles_efectivos ?? user.roles_detalle ?? [];
    const unique = new Map(list.map((role) => [role.id, role]));
    return [...unique.values()];
  });

  protected readonly additionalRoles = computed(() => {
    const principal = this.user()?.rol;
    return this.roles().filter((role) => role.id !== principal);
  });

  protected readonly lastAccess = computed(() => {
    const user = this.user();
    return user?.updated_at ? formatDate(user.updated_at) : '—';
  });

  protected submit(): void {
    this.formError.set(null);
    this.fieldErrors.set({});
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      if (this.form.controls.confirmacion.value !== this.form.controls.contrasena_nueva.value) {
        this.fieldErrors.set({ confirmacion: 'La confirmación no coincide.' });
      }
      return;
    }
    const raw = this.form.getRawValue();
    if (raw.contrasena_nueva !== raw.confirmacion) {
      this.fieldErrors.set({ confirmacion: 'La confirmación no coincide.' });
      return;
    }
    if (raw.contrasena_nueva === raw.contrasena_actual) {
      this.fieldErrors.set({
        contrasena_nueva: 'La nueva contraseña debe ser diferente a la actual.',
      });
      return;
    }

    this.saving.set(true);
    this.api
      .post<{ mensaje: string }>('me/password/', {
        contrasena_actual: raw.contrasena_actual,
        contrasena_nueva: raw.contrasena_nueva,
        confirmacion: raw.confirmacion,
      })
      .subscribe({
        next: (response) => {
          this.saving.set(false);
          this.form.reset({ contrasena_actual: '', contrasena_nueva: '', confirmacion: '' });
          this.toast.success('Contraseña actualizada', response.mensaje);
        },
        error: (error: unknown) => {
          this.saving.set(false);
          if (error instanceof ApiError) {
            const fields = error.fieldErrors();
            this.fieldErrors.set(fields);
            this.formError.set(
              Object.keys(fields).length > 0 ? null : error.message,
            );
          } else {
            this.formError.set('No se pudo cambiar la contraseña.');
          }
        },
      });
  }

  protected fieldError(name: 'contrasena_actual' | 'contrasena_nueva' | 'confirmacion'): string | null {
    return this.fieldErrors()[name] ?? null;
  }
}
