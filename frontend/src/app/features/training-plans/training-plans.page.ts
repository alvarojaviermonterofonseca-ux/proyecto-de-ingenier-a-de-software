import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type {
  ClientProfile,
  ClientTrainerAssignment,
  Exercise,
  TrainingDay,
  TrainingPlan,
  TrainingPlanExercise,
  WeekDay,
} from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { erroresDelServidor, mensajeValidacion } from '../../core/forms/field-errors';
import { WEEK_DAYS, apiPath, muscleLabel, todayCode, toggleMuscle } from '../../core/training/muscles';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { dateInput, formatDate, localDateString } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { Body3dComponent } from '../../shared/body-3d.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { ExerciseThumbComponent } from '../../shared/exercise-thumb.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { MusclePickerComponent } from '../../shared/muscle-picker.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

interface DayView {
  value: WeekDay;
  label: string;
  short: string;
  index: number;
  title: string;
  /** Músculos marcados para el día más los que trabajan sus ejercicios. */
  muscles: string[];
  rows: TrainingPlanExercise[];
  sets: number;
}

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
    Body3dComponent,
    MusclePickerComponent,
    ExerciseThumbComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './training-plans.page.html',
  styleUrl: './training-plans.page.css',
})
export class TrainingPlansPage implements OnInit {
  protected readonly weekDays = WEEK_DAYS;
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly plans = signal<TrainingPlan[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly exercises = signal<Exercise[]>([]);
  protected readonly assignments = signal<ClientTrainerAssignment[]>([]);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly serverErrors = signal<Record<string, string>>({});
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<TrainingPlan | null>(null);

  /** Plan abierto en el panel principal y día elegido. */
  protected readonly selectedId = signal<number | null>(null);
  protected readonly selectedDay = signal<WeekDay>(todayCode());
  protected readonly planExercises = signal<TrainingPlanExercise[]>([]);
  protected readonly exerciseLoading = signal(false);

  /** Editor del día: título, músculos y alta de ejercicios. */
  protected readonly dayEditorOpen = signal(false);
  protected readonly dayTitle = signal('');
  protected readonly dayMuscles = signal<string[]>([]);
  protected readonly daySaving = signal(false);
  protected readonly exerciseSaving = signal(false);
  protected readonly exerciseError = signal<string | null>(null);
  protected readonly exerciseSearch = signal('');

  protected readonly muscleLabel = muscleLabel;
  protected readonly apiPath = apiPath;

  protected readonly isClient = computed(() => this.auth.roleName() === 'cliente');
  protected readonly isTrainer = computed(() => this.auth.roleName() === 'entrenador');
  protected readonly canCreate = computed(() => this.auth.hasPermission('planes-entrenamiento:create'));
  protected readonly canEditPlan = computed(() => this.auth.hasPermission('planes-entrenamiento:edit'));
  protected readonly canManageRows = computed(() =>
    this.auth.hasPermission('planes-entrenamiento-ejercicios:create'),
  );
  protected readonly canDeletePlan = computed(() => this.auth.hasPermission('planes-entrenamiento:delete'));

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const plans = [...this.plans()].sort((a, b) => Number(b.activo) - Number(a.activo));
    if (!query) return plans;
    return plans.filter(
      (plan) =>
        plan.nombre.toLowerCase().includes(query) ||
        plan.cliente_detalle.nombre.toLowerCase().includes(query) ||
        plan.objetivo.toLowerCase().includes(query),
    );
  });

  protected readonly selectedPlan = computed(
    () => this.plans().find((plan) => plan.id === this.selectedId()) ?? null,
  );

  protected readonly days = computed((): DayView[] => {
    const plan = this.selectedPlan();
    const rows = this.planExercises();
    return WEEK_DAYS.map((day, index) => {
      const config: TrainingDay | undefined = plan?.rutina?.[day.value];
      const dayRows = rows.filter((row) => row.dia_semana === day.value).sort((a, b) => a.orden - b.orden);
      const muscles = [
        ...new Set([...(config?.musculos ?? []), ...dayRows.flatMap((row) => row.ejercicio_detalle.musculos ?? [])]),
      ];
      return {
        ...day,
        index,
        title: config?.titulo || (dayRows.length || muscles.length ? 'Entrenamiento' : 'Descanso'),
        muscles,
        rows: dayRows,
        sets: dayRows.reduce((total, row) => total + (row.series ?? 0), 0),
      };
    });
  });

  protected readonly currentDay = computed(
    () => this.days().find((day) => day.value === this.selectedDay()) ?? this.days()[0],
  );

  protected readonly trainingDayCount = computed(
    () => this.days().filter((day) => day.rows.length || day.muscles.length).length,
  );

  protected readonly exerciseOptions = computed(() => {
    const query = this.exerciseSearch().trim().toLowerCase();
    const focus = new Set(this.dayMuscles());
    return this.exercises()
      .filter((exercise) => exercise.is_active)
      .filter((exercise) => !query || exercise.nombre.toLowerCase().includes(query))
      .sort((a, b) => {
        // Primero los ejercicios que trabajan los músculos marcados del día.
        const score = (exercise: Exercise) => (exercise.musculos ?? []).filter((code) => focus.has(code)).length;
        return score(b) - score(a) || a.nombre.localeCompare(b.nombre);
      });
  });

  /** Entrenadores asignados al cliente elegido en el formulario. */
  protected readonly trainerOptions = computed(() => {
    const clientId = Number(this.clientValue());
    return this.assignments()
      .filter((assignment) => assignment.activo && assignment.cliente === clientId)
      .map((assignment) => assignment.entrenador_detalle);
  });

  private readonly clientValue = signal(0);

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required, Validators.min(1)]],
    entrenador: [0, [Validators.required, Validators.min(1)]],
    nombre: ['', [Validators.required, Validators.maxLength(150)]],
    objetivo: ['', [Validators.required, Validators.maxLength(255)]],
    fecha_inicio: [localDateString(new Date()), [Validators.required]],
    fecha_fin: [''],
    activo: [true],
    observaciones: [''],
  });

  protected readonly exerciseForm = this.formBuilder.nonNullable.group({
    ejercicio: [0, [Validators.required, Validators.min(1)]],
    series: [3, [Validators.min(1), Validators.max(20)]],
    repeticiones: [10, [Validators.min(1), Validators.max(200)]],
    peso_kg: [''],
    descanso_segundos: [60, [Validators.min(0), Validators.max(900)]],
    observaciones: [''],
  });

  ngOnInit(): void {
    this.load();
    this.form.controls.cliente.valueChanges.subscribe((value) => {
      this.clientValue.set(Number(value));
      this.syncTrainer();
    });
    if (!this.isClient()) {
      this.api.getAll<ClientProfile>('clientes/', { is_active: true }).subscribe({
        next: (clients) => this.clients.set(clients),
        error: () => this.clients.set([]),
      });
      this.api.getAll<ClientTrainerAssignment>('asignaciones-cliente-entrenador/', { activo: true }).subscribe({
        next: (assignments) => this.assignments.set(assignments),
        error: () => this.assignments.set([]),
      });
    }
    if (this.auth.hasPermission('ejercicios:view')) {
      this.api.getAll<Exercise>('ejercicios/').subscribe({
        next: (exercises) => this.exercises.set(exercises),
        error: () => this.exercises.set([]),
      });
    }
  }

  protected load(selectId?: number): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<TrainingPlan>('planes-entrenamiento/').subscribe({
      next: (plans) => {
        this.plans.set(plans);
        this.loading.set(false);
        const wanted = selectId ?? this.selectedId();
        const plan =
          plans.find((item) => item.id === wanted) ??
          plans.find((item) => item.activo) ??
          plans[0];
        if (plan && plan.id !== this.selectedId()) this.selectPlan(plan);
        else if (!plan) this.selectedId.set(null);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los planes.');
      },
    });
  }

  protected selectPlan(plan: TrainingPlan): void {
    this.selectedId.set(plan.id);
    this.dayEditorOpen.set(false);
    this.loadPlanExercises(plan.id, true);
  }

  protected selectDay(day: WeekDay): void {
    this.selectedDay.set(day);
    if (this.dayEditorOpen()) this.openDayEditor();
  }

  private loadPlanExercises(planId: number, pickDay = false): void {
    this.exerciseLoading.set(true);
    this.api.getAll<TrainingPlanExercise>('planes-entrenamiento-ejercicios/', { plan: planId }).subscribe({
      next: (rows) => {
        if (this.selectedId() !== planId) return;
        this.planExercises.set(rows);
        this.exerciseLoading.set(false);
        if (pickDay) {
          // Abre hoy si le toca entrenar; si no, el primer día con rutina.
          const today = this.days().find((day) => day.value === todayCode());
          const first = this.days().find((day) => day.rows.length || day.muscles.length);
          this.selectedDay.set(today && (today.rows.length || today.muscles.length) ? today.value : first?.value ?? todayCode());
        }
      },
      error: (error: unknown) => {
        this.exerciseLoading.set(false);
        this.toast.error('No se pudieron cargar los ejercicios', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  // ----- Crear y editar el plan -----

  protected fieldError(name: keyof typeof this.form.controls): string | null {
    const server = this.serverErrors()[name];
    if (server) return server;
    const control = this.form.controls[name];
    if (!control.touched || control.valid) return null;
    if (name === 'cliente' && control.errors?.['min']) return 'Elige el cliente que recibirá el plan.';
    if (name === 'entrenador' && control.errors?.['min']) {
      return this.trainerOptions().length
        ? 'Elige el entrenador responsable.'
        : 'Este cliente no tiene un entrenador asignado. Asígnalo primero en Asignaciones.';
    }
    return mensajeValidacion(control);
  }

  private myTrainerId(): number {
    return this.isTrainer() ? this.auth.user()?.id ?? 0 : 0;
  }

  /** El entrenador queda fijo; el administrador elige entre los asignados. */
  private syncTrainer(): void {
    if (this.editing()) return;
    if (this.isTrainer()) {
      this.form.controls.entrenador.setValue(this.myTrainerId());
      return;
    }
    const options = this.trainerOptions();
    const current = this.form.controls.entrenador.value;
    if (!options.some((trainer) => trainer.usuario === current)) {
      this.form.controls.entrenador.setValue(options.length === 1 ? options[0].usuario : 0);
    }
  }

  protected openCreate(clientId = 0): void {
    this.editing.set(null);
    this.formError.set(null);
    this.serverErrors.set({});
    this.form.reset({
      cliente: clientId,
      entrenador: this.myTrainerId(),
      nombre: '',
      objetivo: '',
      fecha_inicio: localDateString(new Date()),
      fecha_fin: '',
      activo: true,
      observaciones: '',
    });
    this.clientValue.set(clientId);
    this.form.controls.cliente.enable();
    this.syncTrainer();
    this.modalOpen.set(true);
  }

  protected openEdit(plan: TrainingPlan): void {
    this.editing.set(plan);
    this.formError.set(null);
    this.serverErrors.set({});
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
    this.clientValue.set(plan.cliente);
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
    this.serverErrors.set({});
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.formError.set('Revisa los campos marcados.');
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
      next: (plan) => {
        this.saving.set(false);
        this.form.controls.cliente.enable();
        this.modalOpen.set(false);
        this.toast.success(
          editing ? 'Plan actualizado' : 'Entrenamiento creado',
          editing ? undefined : 'Ahora arma cada día: músculos y ejercicios.',
        );
        this.load(plan.id);
        if (!editing) {
          this.selectedId.set(plan.id);
          this.planExercises.set([]);
          this.selectedDay.set('lunes');
          this.plans.update((plans) => [plan, ...plans]);
          this.openDayEditor();
        }
      },
      error: (error: unknown) => {
        this.saving.set(false);
        const fields = erroresDelServidor(error);
        this.serverErrors.set(fields);
        this.formError.set(
          Object.keys(fields).length
            ? Object.entries(fields)
                .filter(([field]) => !(field in this.form.controls))
                .map(([, message]) => message)
                .join(' ') || 'Revisa los campos marcados.'
            : error instanceof ApiError
              ? error.message
              : 'No se pudo guardar el plan.',
        );
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
        if (this.selectedId() === plan.id) this.selectedId.set(null);
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  // ----- Editor del día -----

  protected openDayEditor(): void {
    const plan = this.selectedPlan();
    const config = plan?.rutina?.[this.selectedDay()];
    this.dayTitle.set(config?.titulo ?? '');
    this.dayMuscles.set([...(config?.musculos ?? [])]);
    this.exerciseError.set(null);
    this.exerciseSearch.set('');
    this.exerciseForm.reset({
      ejercicio: 0,
      series: 3,
      repeticiones: 10,
      peso_kg: '',
      descanso_segundos: 60,
      observaciones: '',
    });
    this.dayEditorOpen.set(true);
  }

  protected closeDayEditor(): void {
    this.dayEditorOpen.set(false);
  }

  protected saveDay(): void {
    const plan = this.selectedPlan();
    if (!plan) return;
    const rutina = { ...(plan.rutina ?? {}) };
    const title = this.dayTitle().trim();
    if (title || this.dayMuscles().length) {
      rutina[this.selectedDay()] = { titulo: title, musculos: this.dayMuscles() };
    } else {
      delete rutina[this.selectedDay()];
    }
    this.daySaving.set(true);
    this.api.patch<TrainingPlan>(`planes-entrenamiento/${plan.id}/`, { rutina }).subscribe({
      next: (updated) => {
        this.daySaving.set(false);
        this.plans.update((plans) => plans.map((item) => (item.id === updated.id ? updated : item)));
        this.toast.success('Día guardado', `${this.currentDay().label}: ${title || 'sin título'}`);
      },
      error: (error: unknown) => {
        this.daySaving.set(false);
        const fields = erroresDelServidor(error);
        this.toast.error('No se pudo guardar el día', fields['rutina'] ?? (error instanceof ApiError ? error.message : undefined));
      },
    });
  }

  protected exerciseFieldError(name: keyof typeof this.exerciseForm.controls): string | null {
    const control = this.exerciseForm.controls[name];
    if (!control.touched || control.valid) return null;
    if (name === 'ejercicio') return 'Elige el ejercicio.';
    return mensajeValidacion(control);
  }

  protected addExercise(): void {
    const plan = this.selectedPlan();
    this.exerciseError.set(null);
    if (!plan || this.exerciseForm.invalid) {
      this.exerciseForm.markAllAsTouched();
      return;
    }
    const raw = this.exerciseForm.getRawValue();
    const dayRows = this.currentDay().rows;
    const payload = {
      plan: plan.id,
      ejercicio: Number(raw.ejercicio),
      dia_semana: this.selectedDay(),
      orden: dayRows.length ? Math.max(...dayRows.map((row) => row.orden)) + 1 : 1,
      series: raw.series || null,
      repeticiones: raw.repeticiones || null,
      peso_kg: raw.peso_kg === '' ? null : raw.peso_kg,
      descanso_segundos: raw.descanso_segundos === null ? null : raw.descanso_segundos,
      observaciones: raw.observaciones.trim() || null,
    };
    this.exerciseSaving.set(true);
    this.api.post<TrainingPlanExercise>('planes-entrenamiento-ejercicios/', payload).subscribe({
      next: (row) => {
        this.exerciseSaving.set(false);
        this.planExercises.update((rows) => [...rows, row]);
        this.exerciseForm.controls.ejercicio.setValue(0);
        this.exerciseForm.controls.ejercicio.markAsUntouched();
        this.exerciseForm.controls.observaciones.setValue('');
        this.toast.success('Ejercicio agregado', row.ejercicio_detalle.nombre);
      },
      error: (error: unknown) => {
        this.exerciseSaving.set(false);
        const fields = erroresDelServidor(error);
        this.exerciseError.set(
          Object.values(fields).join(' ') || (error instanceof ApiError ? error.message : 'No se pudo agregar.'),
        );
      },
    });
  }

  protected async removeExercise(row: TrainingPlanExercise): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Quitar ejercicio',
      message: `Se quitará ${row.ejercicio_detalle.nombre} del ${this.currentDay().label.toLowerCase()}.`,
      confirmLabel: 'Quitar',
    });
    if (!accepted) return;
    this.api.delete(`planes-entrenamiento-ejercicios/${row.id}/`).subscribe({
      next: () => this.planExercises.update((rows) => rows.filter((item) => item.id !== row.id)),
      error: (error: unknown) => {
        this.toast.error('No se pudo quitar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected toggleDayMuscle(code: string): void {
    this.dayMuscles.update((muscles) => toggleMuscle(muscles, code));
  }

  protected planDays(plan: TrainingPlan): { short: string; title: string }[] {
    return WEEK_DAYS.filter((day) => plan.rutina?.[day.value]).map((day) => ({
      short: day.short,
      title: plan.rutina[day.value]?.titulo || 'Entreno',
    }));
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected kg(value: string): string {
    return String(Number(value));
  }

  protected formatDate = formatDate;
}
