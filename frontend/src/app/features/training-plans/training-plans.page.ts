import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type {
  ClientProfile,
  ClientTrainerAssignment,
  Exercise,
  TrainingDay,
  TrainingDayExerciseInput,
  TrainingDaySaveResponse,
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

/** Ejercicio del día mientras el entrenador lo arma (aún sin guardar). */
interface DraftRow {
  key: number;
  exercise: Exercise;
  series: number | null;
  repeticiones: number | null;
  peso_kg: string;
  descanso_segundos: number | null;
  observaciones: string;
  expanded: boolean;
}

type DraftNumberField = 'series' | 'repeticiones' | 'descanso_segundos';

const LIMITES: Record<DraftNumberField, { min: number; max: number }> = {
  series: { min: 1, max: 20 },
  repeticiones: { min: 1, max: 200 },
  descanso_segundos: { min: 0, max: 900 },
};

const MAX_EJERCICIOS_DIA = 30;

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

  /**
   * Editor del día: el entrenador arma un borrador con varios ejercicios
   * (series y repeticiones de cada uno) y lo guarda completo con un solo botón.
   */
  protected readonly dayEditorOpen = signal(false);
  protected readonly dayTitle = signal('');
  protected readonly dayMuscles = signal<string[]>([]);
  protected readonly musclesOpen = signal(false);
  protected readonly draft = signal<DraftRow[]>([]);
  protected readonly daySaving = signal(false);
  protected readonly editorError = signal<string | null>(null);
  /** Errores del servidor por posición de la fila en el borrador. */
  protected readonly rowErrors = signal<Record<number, string>>({});
  private draftSnapshot = '';
  private nextKey = 1;

  /** Selector múltiple del catálogo de ejercicios. */
  protected readonly pickerOpen = signal(false);
  protected readonly pickerSelected = signal<number[]>([]);
  protected readonly pickerSets = signal<number | null>(3);
  protected readonly pickerReps = signal<number | null>(10);
  protected readonly exerciseSearch = signal('');
  protected readonly maxExercises = MAX_EJERCICIOS_DIA;

  protected readonly muscleLabel = muscleLabel;
  protected readonly apiPath = apiPath;

  protected readonly isClient = computed(() => this.auth.roleName() === 'cliente');
  protected readonly isTrainer = computed(() => this.auth.roleName() === 'entrenador');
  protected readonly canCreate = computed(() => this.auth.hasPermission('planes-entrenamiento:create'));
  protected readonly canEditPlan = computed(() => this.auth.hasPermission('planes-entrenamiento:edit'));
  /** Armar un día reemplaza sus filas: el servidor exige editar plan y filas. */
  protected readonly canBuildDays = computed(
    () =>
      !this.isClient() &&
      this.auth.hasPermission('planes-entrenamiento:edit') &&
      this.auth.hasPermission('planes-entrenamiento-ejercicios:edit'),
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

  protected readonly draftSets = computed(() =>
    this.draft().reduce((total, row) => total + (row.series ?? 0), 0),
  );

  protected readonly draftValid = computed(() =>
    this.draft().every(
      (row) =>
        this.inRange(row.series, 'series') &&
        this.inRange(row.repeticiones, 'repeticiones') &&
        this.inRange(row.descanso_segundos, 'descanso_segundos') &&
        (row.peso_kg === '' || Number(row.peso_kg) >= 0),
    ),
  );

  protected readonly pickedSet = computed(() => new Set(this.pickerSelected()));

  /** Cuántas veces está cada ejercicio en el borrador (para marcarlo en el selector). */
  protected readonly draftCounts = computed(() => {
    const counts = new Map<number, number>();
    for (const row of this.draft()) counts.set(row.exercise.id, (counts.get(row.exercise.id) ?? 0) + 1);
    return counts;
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

  /** Cambiar de plan desde la lista pide confirmar si hay un día sin guardar. */
  protected async choosePlan(plan: TrainingPlan): Promise<void> {
    if (plan.id === this.selectedId() || !(await this.confirmDiscard())) return;
    this.selectPlan(plan);
  }

  protected async selectDay(day: WeekDay): Promise<void> {
    if (day === this.selectedDay()) return;
    const editing = this.dayEditorOpen();
    if (editing && !(await this.confirmDiscard())) return;
    this.selectedDay.set(day);
    if (editing) this.openDayEditor();
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

  // ----- Editor del día (entrenador / administrador) -----

  protected openDayEditor(): void {
    const plan = this.selectedPlan();
    const config = plan?.rutina?.[this.selectedDay()];
    this.dayTitle.set(config?.titulo ?? '');
    this.dayMuscles.set([...(config?.musculos ?? [])]);
    this.draft.set(this.currentDay().rows.map((row) => this.rowFromPlan(row)));
    this.draftSnapshot = this.serializeDraft();
    this.editorError.set(null);
    this.rowErrors.set({});
    this.musclesOpen.set(false);
    this.dayEditorOpen.set(true);
  }

  /** «Cancelar»: descarta el borrador (pide confirmación si hubo cambios). */
  protected async cancelDayEditor(): Promise<void> {
    if (this.daySaving() || !(await this.confirmDiscard())) return;
    this.dayEditorOpen.set(false);
    this.pickerOpen.set(false);
  }

  private async confirmDiscard(): Promise<boolean> {
    if (!this.dayEditorOpen() || this.serializeDraft() === this.draftSnapshot) return true;
    return this.confirm.confirm({
      title: 'Descartar cambios',
      message: `Los cambios del ${this.currentDay().label.toLowerCase()} que no guardaste se perderán.`,
      confirmLabel: 'Descartar',
    });
  }

  private rowFromPlan(row: TrainingPlanExercise): DraftRow {
    return {
      key: this.nextKey++,
      exercise: row.ejercicio_detalle,
      series: row.series,
      repeticiones: row.repeticiones,
      peso_kg: row.peso_kg === null ? '' : this.kg(row.peso_kg),
      descanso_segundos: row.descanso_segundos,
      observaciones: row.observaciones ?? '',
      expanded: false,
    };
  }

  private serializeDraft(): string {
    return JSON.stringify({
      titulo: this.dayTitle().trim(),
      musculos: [...this.dayMuscles()].sort(),
      ejercicios: this.draftPayload(),
    });
  }

  private draftPayload(): TrainingDayExerciseInput[] {
    return this.draft().map((row) => ({
      ejercicio: row.exercise.id,
      series: row.series,
      repeticiones: row.repeticiones,
      peso_kg: row.peso_kg === '' ? null : row.peso_kg,
      descanso_segundos: row.descanso_segundos,
      observaciones: row.observaciones.trim() || null,
    }));
  }

  protected inRange(value: number | null, field: DraftNumberField): boolean {
    if (value === null) return true;
    const { min, max } = LIMITES[field];
    return Number.isInteger(value) && value >= min && value <= max;
  }

  protected setNumber(index: number, field: DraftNumberField, raw: string): void {
    const value = raw.trim() === '' ? null : Number(raw);
    this.patchRow(index, { [field]: Number.isNaN(value) ? null : value });
  }

  protected setText(index: number, field: 'peso_kg' | 'observaciones', value: string): void {
    this.patchRow(index, { [field]: value });
  }

  private patchRow(index: number, patch: Partial<DraftRow>): void {
    this.draft.update((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    if (this.rowErrors()[index]) {
      this.rowErrors.update((errors) => {
        const copy = { ...errors };
        delete copy[index];
        return copy;
      });
    }
  }

  protected toggleRowDetails(index: number): void {
    const row = this.draft()[index];
    if (row) this.patchRow(index, { expanded: !row.expanded });
  }

  protected moveRow(index: number, delta: -1 | 1): void {
    const target = index + delta;
    this.draft.update((rows) => {
      if (target < 0 || target >= rows.length) return rows;
      const copy = [...rows];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });
    this.rowErrors.set({});
  }

  protected removeRow(index: number): void {
    this.draft.update((rows) => rows.filter((_, i) => i !== index));
    this.rowErrors.set({});
  }

  // ----- Selector múltiple de ejercicios -----

  protected openPicker(): void {
    this.pickerSelected.set([]);
    this.exerciseSearch.set('');
    this.pickerOpen.set(true);
  }

  protected closePicker(): void {
    this.pickerOpen.set(false);
  }

  protected togglePick(id: number): void {
    this.pickerSelected.update((ids) => (ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]));
  }

  protected setPickerNumber(target: 'sets' | 'reps', raw: string): void {
    const value = raw.trim() === '' ? null : Number(raw);
    const clean = value === null || Number.isNaN(value) ? null : value;
    (target === 'sets' ? this.pickerSets : this.pickerReps).set(clean);
  }

  protected readonly pickerRoom = computed(() => MAX_EJERCICIOS_DIA - this.draft().length);

  /** Agrega todos los ejercicios marcados al final del día, en el orden en que se marcaron. */
  protected addPicked(): void {
    const byId = new Map(this.exercises().map((exercise) => [exercise.id, exercise]));
    const picked = this.pickerSelected()
      .map((id) => byId.get(id))
      .filter((exercise): exercise is Exercise => !!exercise)
      .slice(0, Math.max(this.pickerRoom(), 0));
    if (!picked.length) return;
    const series = this.inRange(this.pickerSets(), 'series') ? this.pickerSets() : 3;
    const repeticiones = this.inRange(this.pickerReps(), 'repeticiones') ? this.pickerReps() : 10;
    this.draft.update((rows) => [
      ...rows,
      ...picked.map(
        (exercise): DraftRow => ({
          key: this.nextKey++,
          exercise,
          series,
          repeticiones,
          peso_kg: '',
          descanso_segundos: 60,
          observaciones: '',
          expanded: false,
        }),
      ),
    ]);
    // Los músculos de los ejercicios nuevos se marcan en el día (se pueden desmarcar).
    this.dayMuscles.update((muscles) => [
      ...new Set([...muscles, ...picked.flatMap((exercise) => exercise.musculos ?? [])]),
    ]);
    this.pickerOpen.set(false);
    this.toast.success(
      picked.length === 1 ? 'Ejercicio agregado' : `${picked.length} ejercicios agregados`,
      'Ajusta series y repeticiones y pulsa «Guardar plan».',
    );
  }

  // ----- Guardar el día completo -----

  protected saveDayPlan(): void {
    const plan = this.selectedPlan();
    if (!plan || this.daySaving()) return;
    this.editorError.set(null);
    this.rowErrors.set({});
    if (!this.draftValid()) {
      this.editorError.set('Revisa las series y repeticiones marcadas en rojo.');
      return;
    }
    const day = this.selectedDay();
    const body = {
      titulo: this.dayTitle().trim(),
      musculos: this.dayMuscles(),
      ejercicios: this.draftPayload(),
    };
    this.daySaving.set(true);
    this.api.put<TrainingDaySaveResponse>(`planes-entrenamiento/${plan.id}/dias/${day}/`, body).subscribe({
      next: (response) => {
        this.daySaving.set(false);
        this.plans.update((plans) => plans.map((item) => (item.id === response.plan.id ? response.plan : item)));
        this.planExercises.update((rows) => [
          ...rows.filter((row) => row.dia_semana !== day),
          ...response.ejercicios,
        ]);
        this.dayEditorOpen.set(false);
        const count = response.ejercicios.length;
        this.toast.success(
          'Plan guardado',
          `${this.currentDay().label}: ${count} ${count === 1 ? 'ejercicio' : 'ejercicios'} · ${this.currentDay().sets} series`,
        );
      },
      error: (error: unknown) => {
        this.daySaving.set(false);
        this.rowErrors.set(this.rowErrorsFrom(error));
        const fields = erroresDelServidor(error);
        const general = ['titulo', 'musculos', 'rutina', 'entrenador', 'general']
          .map((field) => fields[field])
          .filter(Boolean)
          .join(' ');
        this.editorError.set(
          general ||
            (Object.keys(this.rowErrors()).length
              ? 'Revisa los ejercicios marcados.'
              : error instanceof ApiError
                ? error.message
                : 'No se pudo guardar el día.'),
        );
      },
    });
  }

  /** Errores por fila: DRF los devuelve como lista o como objeto indexado. */
  private rowErrorsFrom(error: unknown): Record<number, string> {
    if (!(error instanceof ApiError) || !error.details || typeof error.details !== 'object') return {};
    const rows = (error.details as Record<string, unknown>)['ejercicios'];
    const result: Record<number, string> = {};
    const text = (value: unknown): string =>
      Array.isArray(value)
        ? value.map(text).filter(Boolean).join(' ')
        : value && typeof value === 'object'
          ? Object.values(value as Record<string, unknown>).map(text).filter(Boolean).join(' ')
          : typeof value === 'string'
            ? value
            : '';
    if (rows && typeof rows === 'object') {
      for (const [index, value] of Object.entries(rows as Record<string, unknown>)) {
        const message = text(value);
        if (message && /^[0-9]+$/.test(index)) result[Number(index)] = message;
      }
    }
    return result;
  }

  protected exerciseSubtitle(exercise: Exercise): string {
    if (exercise.grupo_muscular) return exercise.grupo_muscular;
    return exercise.musculos?.length ? exercise.musculos.map(muscleLabel).join(' · ') : 'Sin músculos marcados';
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
