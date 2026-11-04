import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type {
  ClientProfile,
  Exercise,
  TrainerProfile,
  TrainingPlan,
  TrainingPlanExercise,
  WeekDay,
} from '../../core/api/api.models';
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

@Component({
  selector: 'app-training-plans-page',
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
  templateUrl: './training-plans.page.html',
  styleUrl: './training-plans.page.css',
})
export class TrainingPlansPage implements OnInit {
  protected readonly weekDays: readonly { value: WeekDay; label: string }[] = [
    { value: 'lunes', label: 'Lunes' },
    { value: 'martes', label: 'Martes' },
    { value: 'miercoles', label: 'Miércoles' },
    { value: 'jueves', label: 'Jueves' },
    { value: 'viernes', label: 'Viernes' },
    { value: 'sabado', label: 'Sábado' },
    { value: 'domingo', label: 'Domingo' },
  ];
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly plans = signal<TrainingPlan[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly trainers = signal<TrainerProfile[]>([]);
  protected readonly exercises = signal<Exercise[]>([]);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<TrainingPlan | null>(null);

  protected readonly exercisesModalOpen = signal(false);
  protected readonly planExercises = signal<TrainingPlanExercise[]>([]);
  protected readonly exercisePlan = signal<TrainingPlan | null>(null);
  protected readonly exerciseLoading = signal(false);
  protected readonly exerciseSaving = signal(false);
  protected readonly exerciseError = signal<string | null>(null);

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    if (!query) return this.plans();
    return this.plans().filter(
      (plan) =>
        plan.nombre.toLowerCase().includes(query) ||
        plan.cliente_detalle.nombre.toLowerCase().includes(query) ||
        plan.objetivo.toLowerCase().includes(query),
    );
  });

  protected readonly weeklyRoutine = computed(() => {
    const rows = this.planExercises();
    return this.weekDays.map((day) => {
      const dayRows = rows
        .filter((row) => row.dia_semana === day.value)
        .sort((a, b) => a.orden - b.orden);
      const musculos = [
        ...new Set(
          dayRows
            .map((row) => row.ejercicio_detalle.grupo_muscular)
            .filter((musculo): musculo is string => Boolean(musculo)),
        ),
      ];
      return { ...day, rows: dayRows, musculos };
    });
  });

  protected readonly routineDays = computed(() =>
    this.weeklyRoutine().filter((day) => day.rows.length > 0),
  );

  protected readonly routineMuscles = computed(() => [
    ...new Set(
      this.planExercises()
        .map((row) => row.ejercicio_detalle.grupo_muscular)
        .filter((musculo): musculo is string => Boolean(musculo)),
    ),
  ]);

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required]],
    entrenador: [0, [Validators.required]],
    nombre: ['', [Validators.required]],
    objetivo: ['', [Validators.required]],
    fecha_inicio: [new Date().toISOString().slice(0, 10), [Validators.required]],
    fecha_fin: [''],
    activo: [true],
    observaciones: [''],
  });

  protected readonly exerciseForm = this.formBuilder.nonNullable.group({
    ejercicio: [0, [Validators.required]],
    dia_semana: ['lunes' as WeekDay, [Validators.required]],
    orden: [1, [Validators.required, Validators.min(1)]],
    series: [3],
    repeticiones: [10],
    peso_kg: [''],
    descanso_segundos: [60],
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
    if (this.canManageExercises()) {
      this.api.getAll<Exercise>('ejercicios/').subscribe({
        next: (exercises) => this.exercises.set(exercises),
        error: () => this.exercises.set([]),
      });
    }
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<TrainingPlan>('planes-entrenamiento/').subscribe({
      next: (plans) => {
        this.plans.set(plans);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los planes.');
      },
    });
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      cliente: 0,
      entrenador: 0,
      nombre: '',
      objetivo: '',
      fecha_inicio: new Date().toISOString().slice(0, 10),
      fecha_fin: '',
      activo: true,
      observaciones: '',
    });
    this.form.controls.cliente.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(plan: TrainingPlan): void {
    this.editing.set(plan);
    this.formError.set(null);
    this.form.reset({
      cliente: plan.cliente,
      entrenador: plan.entrenador,
      nombre: plan.nombre,
      objetivo: plan.objetivo,
      fecha_inicio: dateInput(plan.fecha_inicio),
      fecha_fin: dateInput(plan.fecha_fin),
      activo: plan.activo,
      observaciones: plan.observaciones ?? '',
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
      entrenador: raw.entrenador,
      nombre: raw.nombre.trim(),
      objetivo: raw.objetivo.trim(),
      fecha_inicio: raw.fecha_inicio,
      fecha_fin: raw.fecha_fin || null,
      activo: raw.activo,
      observaciones: raw.observaciones.trim() || null,
    };
    if (!editing) payload['cliente'] = raw.cliente;
    this.saving.set(true);
    const request = editing
      ? this.api.patch<TrainingPlan>(`planes-entrenamiento/${editing.id}/`, payload)
      : this.api.post<TrainingPlan>('planes-entrenamiento/', payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.form.controls.cliente.enable();
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Plan actualizado' : 'Plan creado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar el plan.');
      },
    });
  }

  protected async remove(plan: TrainingPlan): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar plan',
      message: `Se eliminará el plan "${plan.nombre}" de ${plan.cliente_detalle.nombre}.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`planes-entrenamiento/${plan.id}/`).subscribe({
      next: () => {
        this.toast.success('Plan eliminado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected openExercises(plan: TrainingPlan): void {
    this.exercisePlan.set(plan);
    this.exerciseError.set(null);
    this.exerciseForm.reset({
      ejercicio: 0,
      dia_semana: 'lunes',
      orden: 1,
      series: 3,
      repeticiones: 10,
      peso_kg: '',
      descanso_segundos: 60,
      observaciones: '',
    });
    this.exercisesModalOpen.set(true);
    this.loadPlanExercises(plan.id);
  }

  protected closeExercises(): void {
    if (!this.exerciseSaving()) {
      this.exercisesModalOpen.set(false);
      this.exercisePlan.set(null);
    }
  }

  protected loadPlanExercises(planId: number): void {
    this.exerciseLoading.set(true);
    this.api.getAll<TrainingPlanExercise>('planes-entrenamiento-ejercicios/', { plan: planId }).subscribe({
      next: (rows) => {
        const orderDay = (dia: WeekDay) => this.weekDays.findIndex((day) => day.value === dia);
        this.planExercises.set(
          [...rows].sort(
            (a, b) => orderDay(a.dia_semana) - orderDay(b.dia_semana) || a.orden - b.orden,
          ),
        );
        this.exerciseLoading.set(false);
        this.updateNextOrder(this.exerciseForm.controls.dia_semana.value);
      },
      error: (error: unknown) => {
        this.exerciseLoading.set(false);
        this.exerciseError.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los ejercicios.');
      },
    });
  }

  protected onDayChange(): void {
    this.updateNextOrder(this.exerciseForm.controls.dia_semana.value);
  }

  private updateNextOrder(dia: WeekDay): void {
    const rows = this.planExercises().filter((row) => row.dia_semana === dia);
    const nextOrder = rows.length > 0 ? Math.max(...rows.map((row) => row.orden)) + 1 : 1;
    this.exerciseForm.controls.orden.setValue(nextOrder);
  }

  protected addExercise(): void {
    const plan = this.exercisePlan();
    if (!plan || this.exerciseForm.invalid) {
      this.exerciseForm.markAllAsTouched();
      return;
    }
    const raw = this.exerciseForm.getRawValue();
    const payload = {
      plan: plan.id,
      ejercicio: raw.ejercicio,
      dia_semana: raw.dia_semana,
      orden: raw.orden,
      series: raw.series || null,
      repeticiones: raw.repeticiones || null,
      peso_kg: raw.peso_kg || null,
      descanso_segundos: raw.descanso_segundos || null,
      observaciones: raw.observaciones.trim() || null,
    };
    this.exerciseSaving.set(true);
    this.api.post('planes-entrenamiento-ejercicios/', payload).subscribe({
      next: () => {
        this.exerciseSaving.set(false);
        this.exerciseForm.controls.ejercicio.setValue(0);
        this.exerciseForm.controls.peso_kg.setValue('');
        this.exerciseForm.controls.observaciones.setValue('');
        this.toast.success('Ejercicio agregado al plan');
        this.loadPlanExercises(plan.id);
      },
      error: (error: unknown) => {
        this.exerciseSaving.set(false);
        this.exerciseError.set(error instanceof ApiError ? error.message : 'No se pudo agregar el ejercicio.');
      },
    });
  }

  protected async removeExercise(row: TrainingPlanExercise): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Quitar ejercicio',
      message: `Se quitará ${row.ejercicio_detalle.nombre} del ${this.dayLabel(row.dia_semana)}.`,
      confirmLabel: 'Quitar',
    });
    if (!accepted) return;
    const plan = this.exercisePlan();
    this.api.delete(`planes-entrenamiento-ejercicios/${row.id}/`).subscribe({
      next: () => {
        if (plan) this.loadPlanExercises(plan.id);
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo quitar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected canManageExercises(): boolean {
    return this.auth.hasPermission('planes-entrenamiento-ejercicios:create');
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected prescription(row: TrainingPlanExercise): string {
    const parts = [];
    if (row.series) parts.push(`${row.series} series`);
    if (row.repeticiones) parts.push(`${row.repeticiones} reps`);
    if (row.peso_kg) parts.push(`${row.peso_kg} kg`);
    if (row.descanso_segundos) parts.push(`${row.descanso_segundos}s descanso`);
    return parts.join(' · ') || 'Sin prescripción';
  }

  protected dayLabel(dia: WeekDay): string {
    return this.weekDays.find((day) => day.value === dia)?.label ?? dia;
  }

  protected formatDate = formatDate;
}
