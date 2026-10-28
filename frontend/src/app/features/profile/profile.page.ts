import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type {
  AdministratorProfile,
  ClientProfile,
  ReceptionistProfile,
  TherapistProfile,
  TrainerProfile,
} from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { ADMIN_LEVELS, dateInput, formatDate } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

type AnyProfile =
  | ClientProfile
  | TrainerProfile
  | TherapistProfile
  | ReceptionistProfile
  | AdministratorProfile;

interface DetailItem {
  label: string;
  value: string;
}

@Component({
  selector: 'app-profile-page',
  standalone: true,
  imports: [
    KeyValuePipe,
    ReactiveFormsModule,
    IconComponent,
    AvatarComponent,
    PageHeaderComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './profile.page.html',
  styleUrl: './profile.page.css',
})
export class ProfilePage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  protected readonly auth = inject(AuthService);

  protected readonly profile = signal<AnyProfile | null>(null);
  protected readonly loadingProfile = signal(false);
  protected readonly identityOpen = signal(false);
  protected readonly passwordOpen = signal(false);
  protected readonly profileOpen = signal(false);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly adminLevels = ADMIN_LEVELS;

  protected readonly roleName = computed(() => this.auth.roleName());
  protected readonly profileEndpoint = computed(() => {
    const endpoints: Record<string, string> = {
      cliente: 'clientes',
      entrenador: 'entrenadores',
      terapeuta: 'terapeutas',
      recepcionista: 'recepcionistas',
      administrador: 'administradores',
    };
    const role = this.roleName();
    return role ? (endpoints[role] ?? null) : null;
  });

  protected readonly canEditIdentity = computed(() => this.auth.hasPermission('usuarios:edit'));
  protected readonly canEditProfile = computed(() => {
    const role = this.roleName();
    return role ? this.auth.hasPermission(`${role === 'cliente' ? 'clientes' : this.profileResource(role)}:edit`) : false;
  });
  protected readonly permissions = computed(() => this.auth.permissions());
  protected readonly permissionList = computed(() => [...this.auth.permissions()].sort());

  protected readonly details = computed<DetailItem[]>(() => {
    const profile = this.profile();
    if (!profile) return [];
    const role = this.roleName();
    if (role === 'cliente') {
      const client = profile as ClientProfile;
      return [
        { label: 'Documento', value: this.document(client.tipo_documento, client.numero_documento) },
        { label: 'Fecha de nacimiento', value: formatDate(client.fecha_nacimiento) },
        { label: 'Objetivo', value: client.objetivo ?? 'Sin definir' },
        { label: 'Peso', value: client.peso_kg ? `${client.peso_kg} kg` : '—' },
        { label: 'Estatura', value: client.estatura_cm ? `${client.estatura_cm} cm` : '—' },
      ];
    }
    if (role === 'entrenador') {
      const trainer = profile as TrainerProfile;
      return [
        { label: 'Especialidad', value: trainer.especialidad ?? '—' },
        { label: 'Certificación', value: trainer.certificacion ?? '—' },
        { label: 'Fecha de ingreso', value: formatDate(trainer.fecha_ingreso) },
        { label: 'Biografía', value: trainer.biografia ?? '—' },
      ];
    }
    if (role === 'terapeuta') {
      const therapist = profile as TherapistProfile;
      return [
        { label: 'Especialidad', value: therapist.especialidad ?? '—' },
        { label: 'Licencia profesional', value: therapist.licencia_profesional ?? '—' },
        { label: 'Fecha de ingreso', value: formatDate(therapist.fecha_ingreso) },
      ];
    }
    if (role === 'recepcionista') {
      const receptionist = profile as ReceptionistProfile;
      return [
        { label: 'Turno preferido', value: this.capitalize(receptionist.turno_preferido) },
        { label: 'Fecha de ingreso', value: formatDate(receptionist.fecha_ingreso) },
      ];
    }
    if (role === 'administrador') {
      const admin = profile as AdministratorProfile;
      return [
        { label: 'Cargo', value: admin.cargo ?? '—' },
        { label: 'Nivel de permisos', value: ADMIN_LEVELS[admin.nivel_permisos] ?? admin.nivel_permisos },
        { label: 'Fecha de ingreso', value: formatDate(admin.fecha_ingreso) },
      ];
    }
    return [];
  });

  protected readonly identityForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required]],
    username: [''],
    correo: ['', [Validators.required, Validators.email]],
    telefono: [''],
  });

  protected readonly passwordForm = this.formBuilder.nonNullable.group(
    {
      contrasena: ['', [Validators.required, Validators.minLength(8)]],
      confirmacion: ['', [Validators.required]],
    },
    { validators: (group) => (group.value.contrasena === group.value.confirmacion ? null : { mismatch: true }) },
  );

  protected readonly profileForm = this.formBuilder.nonNullable.group({
    tipo_documento: [''],
    numero_documento: [''],
    fecha_nacimiento: [''],
    objetivo: [''],
    peso_kg: [''],
    estatura_cm: [''],
    especialidad: [''],
    certificacion: [''],
    licencia_profesional: [''],
    fecha_ingreso: [''],
    biografia: [''],
    turno_preferido: [''],
    cargo: [''],
    nivel_permisos: ['gestion'],
  });

  ngOnInit(): void {
    this.fillIdentity();
    this.loadProfile();
  }

  protected openIdentity(): void {
    this.formError.set(null);
    this.fillIdentity();
    this.identityOpen.set(true);
  }

  protected openPassword(): void {
    this.formError.set(null);
    this.passwordForm.reset({ contrasena: '', confirmacion: '' });
    this.passwordOpen.set(true);
  }

  protected openProfile(): void {
    this.formError.set(null);
    this.fillProfileForm();
    this.profileOpen.set(true);
  }

  protected closeIdentity(): void {
    if (!this.saving()) this.identityOpen.set(false);
  }

  protected closePassword(): void {
    if (!this.saving()) this.passwordOpen.set(false);
  }

  protected closeProfile(): void {
    if (!this.saving()) this.profileOpen.set(false);
  }

  protected saveIdentity(): void {
    this.formError.set(null);
    const user = this.auth.user();
    if (!user || this.identityForm.invalid) {
      this.identityForm.markAllAsTouched();
      return;
    }
    const raw = this.identityForm.getRawValue();
    const payload = {
      nombre: raw.nombre.trim(),
      username: raw.username.trim() || null,
      correo: raw.correo.trim().toLowerCase(),
      telefono: raw.telefono.trim() || null,
    };
    this.saving.set(true);
    this.api.patch(`usuarios/${user.id}/`, payload).subscribe({
      next: () => {
        this.saving.set(false);
        this.identityOpen.set(false);
        this.toast.success('Datos actualizados');
        this.auth.refresh().subscribe({
          next: () => this.fillIdentity(),
          error: () => undefined,
        });
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudieron guardar los datos.');
      },
    });
  }

  protected savePassword(): void {
    this.formError.set(null);
    const user = this.auth.user();
    if (!user || this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.api
      .patch(`usuarios/${user.id}/`, {
        contrasena: this.passwordForm.controls.contrasena.value,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.passwordOpen.set(false);
          this.toast.success('Contraseña actualizada', 'Inicia sesión de nuevo con tu nueva contraseña.');
          this.auth.clearSession();
          void this.router.navigate(['/login']);
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.formError.set(
            error instanceof ApiError ? error.message : 'No se pudo actualizar la contraseña.',
          );
        },
      });
  }

  protected saveProfile(): void {
    this.formError.set(null);
    const user = this.auth.user();
    const endpoint = this.profileEndpoint();
    if (!user || !endpoint) return;
    this.saving.set(true);
    this.api.patch(`${endpoint}/${user.id}/`, this.profilePayload()).subscribe({
      next: () => {
        this.saving.set(false);
        this.profileOpen.set(false);
        this.toast.success('Perfil actualizado');
        this.loadProfile();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo actualizar el perfil.');
      },
    });
  }

  protected async logoutEverywhere(): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Cerrar todas las sesiones',
      message: 'Se revocarán todas las sesiones activas, incluida esta. Tendrás que iniciar sesión de nuevo.',
      confirmLabel: 'Cerrar sesiones',
    });
    if (!accepted) return;
    this.auth.logoutAll().subscribe({
      next: () => {
        void this.router.navigate(['/login']);
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudieron cerrar las sesiones',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  private loadProfile(): void {
    const user = this.auth.user();
    const endpoint = this.profileEndpoint();
    if (!user || !endpoint) {
      this.profile.set(null);
      return;
    }
    this.loadingProfile.set(true);
    this.api.get<AnyProfile>(`${endpoint}/${user.id}/`).subscribe({
      next: (profile) => {
        this.profile.set(profile);
        this.loadingProfile.set(false);
      },
      error: () => {
        this.profile.set(null);
        this.loadingProfile.set(false);
      },
    });
  }

  private fillIdentity(): void {
    const user = this.auth.user();
    if (!user) return;
    this.identityForm.reset({
      nombre: user.nombre,
      username: user.username ?? '',
      correo: user.correo,
      telefono: user.telefono ?? '',
    });
  }

  private fillProfileForm(): void {
    const profile = this.profile();
    if (!profile) return;
    this.profileForm.reset({
      tipo_documento: 'tipo_documento' in profile ? (profile.tipo_documento ?? '') : '',
      numero_documento: 'numero_documento' in profile ? (profile.numero_documento ?? '') : '',
      fecha_nacimiento: 'fecha_nacimiento' in profile ? dateInput(profile.fecha_nacimiento) : '',
      objetivo: 'objetivo' in profile ? (profile.objetivo ?? '') : '',
      peso_kg: 'peso_kg' in profile ? (profile.peso_kg ?? '') : '',
      estatura_cm: 'estatura_cm' in profile ? (profile.estatura_cm ?? '') : '',
      especialidad: 'especialidad' in profile ? (profile.especialidad ?? '') : '',
      certificacion: 'certificacion' in profile ? (profile.certificacion ?? '') : '',
      licencia_profesional:
        'licencia_profesional' in profile ? (profile.licencia_profesional ?? '') : '',
      fecha_ingreso: 'fecha_ingreso' in profile ? dateInput(profile.fecha_ingreso) : '',
      biografia: 'biografia' in profile ? (profile.biografia ?? '') : '',
      turno_preferido: 'turno_preferido' in profile ? (profile.turno_preferido ?? '') : '',
      cargo: 'cargo' in profile ? (profile.cargo ?? '') : '',
      nivel_permisos: 'nivel_permisos' in profile ? profile.nivel_permisos : 'gestion',
    });
  }

  private profilePayload(): Record<string, unknown> {
    const raw = this.profileForm.getRawValue();
    const role = this.roleName();
    if (role === 'cliente') {
      return {
        tipo_documento: raw.tipo_documento.trim() || null,
        numero_documento: raw.numero_documento.trim() || null,
        fecha_nacimiento: raw.fecha_nacimiento || null,
        objetivo: raw.objetivo.trim() || null,
        peso_kg: raw.peso_kg || null,
        estatura_cm: raw.estatura_cm || null,
      };
    }
    if (role === 'entrenador') {
      return {
        especialidad: raw.especialidad.trim() || null,
        certificacion: raw.certificacion.trim() || null,
        fecha_ingreso: raw.fecha_ingreso || null,
        biografia: raw.biografia.trim() || null,
      };
    }
    if (role === 'terapeuta') {
      return {
        especialidad: raw.especialidad.trim() || null,
        licencia_profesional: raw.licencia_profesional.trim() || null,
        fecha_ingreso: raw.fecha_ingreso || null,
      };
    }
    if (role === 'recepcionista') {
      return {
        fecha_ingreso: raw.fecha_ingreso || null,
        turno_preferido: raw.turno_preferido || null,
      };
    }
    return {
      cargo: raw.cargo.trim() || null,
      fecha_ingreso: raw.fecha_ingreso || null,
      nivel_permisos: raw.nivel_permisos,
    };
  }

  private profileResource(role: string): string {
    const resources: Record<string, string> = {
      entrenador: 'entrenadores',
      terapeuta: 'terapeutas',
      recepcionista: 'recepcionistas',
      administrador: 'administradores',
    };
    return resources[role] ?? 'usuarios';
  }

  private document(tipo: string | null, numero: string | null): string {
    if (!tipo && !numero) return '—';
    return [tipo, numero].filter(Boolean).join(' ');
  }

  private capitalize(value: string | null | undefined): string {
    if (!value) return '—';
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  protected formatDate = formatDate;
}
