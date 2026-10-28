import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';
import { ToastService } from '../../core/ui/toast.service';
import { ADMIN_LEVELS, dateInput, formatDate, humanize } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

type TeamKind = 'entrenadores' | 'terapeutas' | 'recepcionistas' | 'administradores';

interface TeamKindConfig {
  kind: TeamKind;
  label: string;
  singular: string;
  icon: string;
  permission: string;
  description: string;
}

interface TeamProfileRow {
  usuario: number;
  usuario_detalle: {
    id: number;
    nombre: string;
    correo: string;
    telefono: string | null;
    is_active: boolean;
  };
  is_active: boolean;
  especialidad?: string | null;
  certificacion?: string | null;
  licencia_profesional?: string | null;
  biografia?: string | null;
  cargo?: string | null;
  nivel_permisos?: string;
  fecha_ingreso?: string | null;
  turno_preferido?: string | null;
}

const TEAM_KINDS: readonly TeamKindConfig[] = [
  {
    kind: 'entrenadores',
    label: 'Entrenadores',
    singular: 'entrenador',
    icon: 'dumbbell',
    permission: 'entrenadores:view',
    description: 'Profesionales que acompañan el entrenamiento y los planes.',
  },
  {
    kind: 'terapeutas',
    label: 'Terapeutas',
    singular: 'terapeuta',
    icon: 'activity',
    permission: 'terapeutas:view',
    description: 'Equipo terapéutico y seguimiento clínico de clientes.',
  },
  {
    kind: 'recepcionistas',
    label: 'Recepción',
    singular: 'recepcionista',
    icon: 'clock',
    permission: 'recepcionistas:view',
    description: 'Personal que gestiona el acceso y la operación diaria.',
  },
  {
    kind: 'administradores',
    label: 'Administración',
    singular: 'administrador',
    icon: 'shield',
    permission: 'administradores:view',
    description: 'Cuentas con capacidad de gestión global del gimnasio.',
  },
];

@Component({
  selector: 'app-team-page',
  standalone: true,
  imports: [
    RouterLink,
    ReactiveFormsModule,
    IconComponent,
    AvatarComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './team.page.html',
  styleUrl: './team.page.css',
})
export class TeamPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly kinds = computed(() =>
    TEAM_KINDS.filter((kind) => this.auth.hasPermission(kind.permission)),
  );
  protected readonly activeKind = signal<TeamKind | null>(null);
  protected readonly activeConfig = computed(
    () => this.kinds().find((kind) => kind.kind === this.activeKind()) ?? null,
  );
  protected readonly profiles = signal<TeamProfileRow[]>([]);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<TeamProfileRow | null>(null);

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    if (!query) return this.profiles();
    return this.profiles().filter(
      (profile) =>
        profile.usuario_detalle.nombre.toLowerCase().includes(query) ||
        profile.usuario_detalle.correo.toLowerCase().includes(query),
    );
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    especialidad: [''],
    certificacion: [''],
    licencia_profesional: [''],
    biografia: [''],
    cargo: [''],
    nivel_permisos: ['operativo'],
    fecha_ingreso: [''],
    turno_preferido: [''],
    is_active: [true],
  });

  ngOnInit(): void {
    this.activeKind.set(this.kinds()[0]?.kind ?? null);
    this.load();
  }

  protected selectKind(kind: TeamKind): void {
    this.activeKind.set(kind);
    this.search.set('');
    this.load();
  }

  protected load(): void {
    const kind = this.activeKind();
    if (!kind) {
      this.loading.set(false);
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<TeamProfileRow>(kind).subscribe({
      next: (profiles) => {
        this.profiles.set(profiles);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudo cargar el equipo.');
      },
    });
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected canCreate(): boolean {
    return (
      this.auth.isAdmin() &&
      this.auth.hasPermission('usuarios:view') &&
      this.auth.hasPermission('usuarios:create')
    );
  }

  protected openEdit(profile: TeamProfileRow): void {
    this.editing.set(profile);
    this.formError.set(null);
    this.form.reset({
      especialidad: profile.especialidad ?? '',
      certificacion: profile.certificacion ?? '',
      licencia_profesional: profile.licencia_profesional ?? '',
      biografia: profile.biografia ?? '',
      cargo: profile.cargo ?? '',
      nivel_permisos: profile.nivel_permisos ?? 'operativo',
      fecha_ingreso: dateInput(profile.fecha_ingreso),
      turno_preferido: profile.turno_preferido ?? '',
      is_active: profile.is_active,
    });
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) this.modalOpen.set(false);
  }

  protected save(): void {
    const profile = this.editing();
    const kind = this.activeKind();
    if (!profile || !kind) return;
    const raw = this.form.getRawValue();
    const payload: Record<string, unknown> = { is_active: raw.is_active };
    const fields: Record<TeamKind, string[]> = {
      entrenadores: ['especialidad', 'certificacion', 'fecha_ingreso', 'biografia'],
      terapeutas: ['especialidad', 'licencia_profesional', 'fecha_ingreso'],
      recepcionistas: ['fecha_ingreso', 'turno_preferido'],
      administradores: ['cargo', 'fecha_ingreso', 'nivel_permisos'],
    };
    for (const field of fields[kind]) {
      const value = String(raw[field as keyof typeof raw] ?? '').trim();
      payload[field] = value || null;
    }
    this.saving.set(true);
    this.api.patch(`${kind}/${profile.usuario}/`, payload).subscribe({
      next: () => {
        this.saving.set(false);
        this.modalOpen.set(false);
        this.toast.success('Perfil actualizado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo actualizar el perfil.');
      },
    });
  }

  protected editPermission(): boolean {
    const kind = this.activeKind();
    return kind ? this.auth.hasPermission(`${kind}:edit`) : false;
  }

  protected secondary(profile: TeamProfileRow): string {
    const kind = this.activeKind();
    if (kind === 'entrenadores' || kind === 'terapeutas') {
      return profile.especialidad || 'Sin especialidad';
    }
    if (kind === 'recepcionistas') {
      return profile.turno_preferido ? `Turno ${profile.turno_preferido}` : 'Sin turno definido';
    }
    return profile.cargo || ADMIN_LEVELS[profile.nivel_permisos ?? ''] || 'Sin cargo';
  }

  protected formatDate = formatDate;
  protected humanize = humanize;
}
