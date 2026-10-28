import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { ClientProfile, TrainerProfile, Workout } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { dateTimeInput, formatDateTime, toIso } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-workouts-page',
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
  templateUrl: './workouts.page.html',
  styleUrl: './workouts.page.css',
})
export class WorkoutsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);

  protected readonly workouts = signal<Workout[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly trainers = signal<TrainerProfile[]>([]);
  protected readonly search = signal('');
  protected readonly statusFilter = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<Workout | null>(null);

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const status = this.statusFilter();
    return this.workouts().filter((workout) => {
      if (status === 'open' && workout.fin_at) return false;
      if (status === 'closed' && !workout.fin_at) return false;
      if (!query) return true;
      return (
        workout.cliente_detalle.nombre.toLowerCase().includes(query) ||
        (workout.entrenador_detalle?.nombre ?? '').toLowerCase().includes(query)
      );
    });
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required]],
    entrenador: [0],
    inicio_at: [dateTimeInput(new Date().toISOString()), [Validators.required]],
    fin_at: [''],
    observaciones: [''],
  });

  ngOnInit(): void {
    this.load();
    this.api.getAll<ClientProfile>('clientes/', { is_active: true }).subscribe({
      next: (clients) => this.clients.set(clients),
      error: () => this.clients.set([]),
    });
    this.api.getAll<TrainerProfile>('entrenadores/').subscribe({
      next: (trainers) => this.trainers.set(trainers),
      error: () => this.trainers.set([]),
    });
    if (
      this.route.snapshot.queryParamMap.get('nuevo') === '1' &&
      this.auth.hasPermission('entrenamientos:create')
    ) {
      this.openCreate();
    }
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Workout>('entrenamientos/').subscribe({
      next: (workouts) => {
        this.workouts.set(
          workouts.sort((a, b) => new Date(b.inicio_at).getTime() - new Date(a.inicio_at).getTime()),
        );
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los entrenamientos.');
      },
    });
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      cliente: 0,
      entrenador: 0,
      inicio_at: dateTimeInput(new Date().toISOString()),
      fin_at: '',
      observaciones: '',
    });
    this.form.controls.cliente.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(workout: Workout): void {
    this.editing.set(workout);
    this.formError.set(null);
    this.form.reset({
      cliente: workout.cliente,
      entrenador: workout.entrenador ?? 0,
      inicio_at: dateTimeInput(workout.inicio_at),
      fin_at: dateTimeInput(workout.fin_at),
      observaciones: workout.observaciones ?? '',
    });
    this.form.controls.cliente.disable();
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.form.controls.cliente.enable();
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
      entrenador: raw.entrenador || null,
      inicio_at: toIso(raw.inicio_at),
      fin_at: toIso(raw.fin_at),
      observaciones: raw.observaciones.trim() || null,
    };
    if (!editing) payload['cliente'] = raw.cliente;
    this.saving.set(true);
    const request = editing
      ? this.api.patch<Workout>(`entrenamientos/${editing.id}/`, payload)
      : this.api.post<Workout>('entrenamientos/', payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.form.controls.cliente.enable();
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Entrenamiento actualizado' : 'Entrenamiento creado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar el entrenamiento.');
      },
    });
  }

  protected async remove(workout: Workout): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar entrenamiento',
      message: `Se eliminará la sesión de ${workout.cliente_detalle.nombre} del ${formatDateTime(workout.inicio_at)}.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`entrenamientos/${workout.id}/`).subscribe({
      next: () => {
        this.toast.success('Entrenamiento eliminado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected formatDateTime = formatDateTime;
}
