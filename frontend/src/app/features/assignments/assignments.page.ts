import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { ClientProfile } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { dateInput, formatDate } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

type AssignmentKind = 'asignaciones-cliente-entrenador' | 'clientes-terapeutas';

interface Professional {
  usuario: number;
  usuario_detalle: { id: number; nombre: string; correo: string };
  especialidad?: string | null;
}

interface AssignmentRow {
  id: number;
  cliente: number;
  cliente_detalle: { usuario: number; nombre: string; correo: string };
  entrenador?: number;
  entrenador_detalle?: { usuario: number; nombre: string; correo: string; especialidad: string | null };
  terapeuta?: number;
  terapeuta_detalle?: { usuario: number; nombre: string; correo: string; especialidad: string | null };
  fecha_inicio: string;
  fecha_fin: string | null;
  activo: boolean;
}

interface AssignmentConfig {
  kind: AssignmentKind;
  label: string;
  singular: string;
  icon: string;
  description: string;
  viewPermission: string;
  createPermission: string;
  editPermission: string;
  deletePermission: string;
  professionalLabel: string;
}

const CONFIGS: readonly AssignmentConfig[] = [
  {
    kind: 'asignaciones-cliente-entrenador',
    label: 'Cliente · Entrenador',
    singular: 'asignación',
    icon: 'dumbbell',
    description: 'Vincula cada cliente con su entrenador responsable.',
    viewPermission: 'asignaciones-cliente-entrenador:view',
    createPermission: 'asignaciones-cliente-entrenador:create',
    editPermission: 'asignaciones-cliente-entrenador:edit',
    deletePermission: 'asignaciones-cliente-entrenador:delete',
    professionalLabel: 'Entrenador',
  },
  {
    kind: 'clientes-terapeutas',
    label: 'Cliente · Terapeuta',
    singular: 'asignación',
    icon: 'activity',
    description: 'Vincula cada cliente con su terapeuta de seguimiento.',
    viewPermission: 'clientes-terapeutas:view',
    createPermission: 'clientes-terapeutas:create',
    editPermission: 'clientes-terapeutas:edit',
    deletePermission: 'clientes-terapeutas:delete',
    professionalLabel: 'Terapeuta',
  },
];

@Component({
  selector: 'app-assignments-page',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    IconComponent,
    AvatarComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './assignments.page.html',
  styleUrl: './assignments.page.css',
})
export class AssignmentsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly configs = computed(() =>
    CONFIGS.filter((config) => this.auth.hasPermission(config.viewPermission)),
  );
  protected readonly activeKind = signal<AssignmentKind | null>(null);
  protected readonly activeConfig = computed(
    () => this.configs().find((config) => config.kind === this.activeKind()) ?? null,
  );

  protected readonly assignments = signal<AssignmentRow[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly professionals = signal<Professional[]>([]);
  protected readonly search = signal('');
  protected readonly activeFilter = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<AssignmentRow | null>(null);

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    return this.assignments().filter((assignment) => {
      if (!query) return true;
      const professional = this.professionalName(assignment).toLowerCase();
      return (
        assignment.cliente_detalle.nombre.toLowerCase().includes(query) ||
        professional.includes(query)
      );
    });
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required]],
    profesional: [0, [Validators.required]],
    fecha_inicio: ['', [Validators.required]],
    fecha_fin: [''],
    activo: [true],
  });

  ngOnInit(): void {
    this.activeKind.set(this.configs()[0]?.kind ?? null);
    this.loadClients();
    this.load();
  }

  protected selectKind(kind: AssignmentKind): void {
    this.activeKind.set(kind);
    this.search.set('');
    this.activeFilter.set('');
    this.load();
    this.loadProfessionals();
  }

  protected load(): void {
    const kind = this.activeKind();
    if (!kind) {
      this.loading.set(false);
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<AssignmentRow>(kind, { activo: this.activeFilter() || null }).subscribe({
      next: (assignments) => {
        this.assignments.set(assignments);
        this.loading.set(false);
        this.loadProfessionals();
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar las asignaciones.');
      },
    });
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected updateActiveFilter(value: string): void {
    this.activeFilter.set(value);
    this.load();
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      cliente: 0,
      profesional: 0,
      fecha_inicio: new Date().toISOString().slice(0, 10),
      fecha_fin: '',
      activo: true,
    });
    this.modalOpen.set(true);
  }

  protected openEdit(assignment: AssignmentRow): void {
    this.editing.set(assignment);
    this.formError.set(null);
    this.form.reset({
      cliente: assignment.cliente,
      profesional: this.professionalId(assignment),
      fecha_inicio: dateInput(assignment.fecha_inicio),
      fecha_fin: dateInput(assignment.fecha_fin),
      activo: assignment.activo,
    });
    this.form.controls.cliente.disable();
    this.form.controls.profesional.disable();
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.form.controls.cliente.enable();
      this.form.controls.profesional.enable();
      this.modalOpen.set(false);
    }
  }

  protected save(): void {
    const config = this.activeConfig();
    if (!config) return;
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const payload: Record<string, unknown> = {
      cliente: raw.cliente,
      fecha_inicio: raw.fecha_inicio,
      fecha_fin: raw.fecha_fin || null,
      activo: raw.activo,
    };
    payload[config.kind === 'clientes-terapeutas' ? 'terapeuta' : 'entrenador'] = raw.profesional;
    const editing = this.editing();
    this.saving.set(true);
    const request = editing
      ? this.api.patch(`${config.kind}/${editing.id}/`, payload)
      : this.api.post(`${config.kind}/`, payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.form.controls.cliente.enable();
        this.form.controls.profesional.enable();
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Asignación actualizada' : 'Asignación creada');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar la asignación.');
      },
    });
  }

  protected async remove(assignment: AssignmentRow): Promise<void> {
    const config = this.activeConfig();
    if (!config) return;
    const accepted = await this.confirm.confirm({
      title: 'Eliminar asignación',
      message: `Se eliminará el vínculo entre ${assignment.cliente_detalle.nombre} y ${this.professionalName(assignment)}.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`${config.kind}/${assignment.id}/`).subscribe({
      next: () => {
        this.toast.success('Asignación eliminada');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected professionalName(assignment: AssignmentRow): string {
    return (
      assignment.entrenador_detalle?.nombre ??
      assignment.terapeuta_detalle?.nombre ??
      '—'
    );
  }

  protected professionalId(assignment: AssignmentRow): number {
    return assignment.entrenador ?? assignment.terapeuta ?? 0;
  }

  protected formatDate = formatDate;

  private professionalIdOf(item: Professional): number {
    return item.usuario;
  }

  private loadClients(): void {
    this.api.getAll<ClientProfile>('clientes/', { is_active: true }).subscribe({
      next: (clients) => this.clients.set(clients),
      error: () => this.clients.set([]),
    });
  }

  private loadProfessionals(): void {
    const kind = this.activeKind();
    if (!kind) return;
    const endpoint = kind === 'clientes-terapeutas' ? 'terapeutas' : 'entrenadores';
    this.api.getAll<Professional>(endpoint).subscribe({
      next: (professionals) => this.professionals.set(professionals),
      error: () => this.professionals.set([]),
    });
  }

  protected professionalValue(professional: Professional): number {
    return this.professionalIdOf(professional);
  }
}
