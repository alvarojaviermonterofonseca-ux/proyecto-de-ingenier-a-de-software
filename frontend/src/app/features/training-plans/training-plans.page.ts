import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Observable, catchError, concatMap, from, map, throwError } from 'rxjs';

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
import {
  WEEK_DAYS,
  apiPath,
  findMuscle,
  isGroupCode,
  muscleLabel,
  todayCode,
  toggleMuscle,
} from '../../core/training/muscles';
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

/** Un día de la semana en el borrador: nombre, músculos y ejercicios. */
interface DayDraft {
  titulo: string;
  musculos: string[];
  rows: DraftRow[];
}

type WeekDraft = Record<WeekDay, DayDraft>;

/**
 * ``closed``: solo se ve el plan. ``edit``: se arma la semana de un plan que
 * ya existe (panel principal). ``create``: se arma dentro de «Crear entrenamiento».
 */
type BuilderMode = 'closed' | 'edit' | 'create';

type DraftNumberField = 'series' | 'repeticiones' | 'descanso_segundos';

const LIMITES: Record<DraftNumberField, { min: number; max: number }> = {
  series: { min: 1, max: 20 },
  repeticiones: { min: 1, max: 200 },
  descanso_segundos: { min: 0, max: 900 },
};

const MAX_EJERCICIOS_DIA = 30;

function emptyWeek(): WeekDraft {
  return Object.fromEntries(
    WEEK_DAYS.map((day) => [day.value, { titulo: '', musculos: [], rows: [] }]),
  ) as unknown as WeekDraft;
}

@Component({
  selector: 'app-training-plans-page',
  standalone: true,
  imports: [
    NgTemplateOutlet,
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

  // ----- Armado de la semana (crear o editar) -----

  protected readonly builderMode = signal<BuilderMode>('closed');
  protected readonly week = signal<WeekDraft>(emptyWeek());
  protected readonly builderDay = signal<WeekDay>('lunes');
  protected readonly musclesOpen = signal(false);
  protected readonly daySaving = signal(false);
  protected readonly editorError = signal<string | null>(null);
  /** Errores del servidor por posición de la fila en el día abierto. */
  protected readonly rowErrors = signal<Record<number, string>>({});
  /** Cómo estaba cada día al abrir el editor (para saber qué cambió). */
  private weekSnapshot: Partial<Record<WeekDay, string>> = {};
  /** Plan ya creado cuyo guardado de días falló: el reintento no lo crea de nuevo. */
  private createdPlan: TrainingPlan | null = null;
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
  /** Armar días reemplaza sus filas: el servidor exige editar plan y filas. */
  protected readonly canBuildDays = computed(
    () =>
      !this.isClient() &&
      this.auth.hasPermission('planes-entrenamiento:edit') &&
      this.auth.hasPermission('planes-entrenamiento-ejercicios:edit'),
  );
  protected readonly canDeletePlan = computed(() => this.auth.hasPermission('planes-entrenamiento:delete'));

  /** El editor del panel principal (plan existente) está abierto. */
  protected readonly dayEditorOpen = computed(() => this.builderMode() === 'edit');
  /** «Crear entrenamiento» incluye el armado de la semana. */
  protected readonly createWithRoutine = computed(
    () => this.builderMode() === 'create' && this.canBuildDays(),
  );

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

  // ----- Vista del día abierto en el editor -----

  protected readonly builderDayInfo = computed(() => {
    const index = WEEK_DAYS.findIndex((day) => day.value === this.builderDay());
    return { ...WEEK_DAYS[Math.max(index, 0)], index: Math.max(index, 0) };
  });
  private readonly openDay = computed(() => this.week()[this.builderDay()]);
  protected readonly draft = computed(() => this.openDay().rows);
  protected readonly dayTitle = computed(() => this.openDay().titulo);
  protected readonly dayMuscles = computed(() => this.openDay().musculos);

  protected readonly draftSets = computed(() =>
    this.draft().reduce((total, row) => total + (row.series ?? 0), 0),
  );

  /** Pestañas del editor: nombre, ejercicios y series de cada día del borrador. */
  protected readonly builderTabs = computed(() =>
    WEEK_DAYS.map((day) => {
      const draft = this.week()[day.value];
      return {
        ...day,
        titulo: draft.titulo.trim(),
        count: draft.rows.length,
        active: !!(draft.titulo.trim() || draft.musculos.length || draft.rows.length),
        invalid: !draft.rows.every((row) => this.rowValid(row)),
      };
    }),
  );

  protected readonly weekTotals = computed(() => {
    const days = Object.values(this.week());
    return {
      days: days.filter((day) => day.rows.length || day.titulo.trim() || day.musculos.length).length,
      exercises: days.reduce((total, day) => total + day.rows.length, 0),
      sets: days.reduce((total, day) => total + day.rows.reduce((sum, row) => sum + (row.series ?? 0), 0), 0),
    };
  });

  protected readonly weekValid = computed(() =>
    Object.values(this.week()).every((day) => day.rows.every((row) => this.rowValid(row))),
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

  protected readonly pickedSet = computed(() => new Set(this.pickerSelected()));

  /** Cuántas veces está cada ejercicio en el día abierto (para marcarlo en el selector). */
  protected readonly draftCounts = computed(() => {
    const counts = new Map<number, number>();
    for (const row of this.draft()) counts.set(row.exercise.id, (counts.get(row.exercise.id) ?? 0) + 1);
    return counts;
  });

  protected readonly pickerRoom = computed(() => MAX_EJERCICIOS_DIA - this.draft().length);

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
    if (this.builderMode() === 'edit') this.builderMode.set('closed');
    this.loadPlanExercises(plan.id, true);
  }

  /** Cambiar de plan desde la lista pide confirmar si hay cambios sin guardar. */
  protected async choosePlan(plan: TrainingPlan): Promise<void> {
    if (plan.id === this.selectedId() || !(await this.confirmDiscard())) return;
    this.selectPlan(plan);
  }

  /** Con el editor abierto, cambiar de día no descarta nada: toda la semana es un borrador. */
  protected selectDay(day: WeekDay): void {
    this.selectedDay.set(day);
    if (this.builderMode() !== 'closed') this.selectBuilderDay(day);
  }

  protected selectBuilderDay(day: WeekDay): void {
    this.builderDay.set(day);
    this.rowErrors.set({});
    this.musclesOpen.set(false);
    if (this.builderMode() === 'edit') this.selectedDay.set(day);
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

  /** «Crear entrenamiento»: datos del plan y, en la misma ventana, la semana con sus ejercicios. */
  protected async openCreate(clientId = 0): Promise<void> {
    if (this.builderMode() === 'edit' && !(await this.confirmDiscard())) return;
    this.editing.set(null);
    this.createdPlan = null;
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
    this.startBuilder('create', emptyWeek(), 'lunes');
    this.modalOpen.set(true);
  }

  protected openEdit(plan: TrainingPlan): void {
    if (this.builderMode() === 'edit') this.builderMode.set('closed');
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

  protected async closeModal(): Promise<void> {
    if (this.saving()) return;
    if (this.builderMode() === 'create' && !(await this.confirmDiscard())) return;
    this.form.controls.cliente.enable();
    this.modalOpen.set(false);
    if (this.builderMode() === 'create') this.closeBuilder();
    if (this.createdPlan) {
      // El plan se creó aunque faltaron días: se muestra para terminarlo con «Armar».
      const plan = this.createdPlan;
      this.createdPlan = null;
      this.load(plan.id);
    }
  }

  protected save(): void {
    this.formError.set(null);
    this.serverErrors.set({});
    this.editorError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.formError.set('Revisa los campos marcados.');
      return;
    }
    if (this.createWithRoutine() && !this.weekValid()) {
      this.focusFirstInvalidDay();
      this.formError.set('Revisa las series y repeticiones marcadas en rojo en la rutina.');
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

    if (!editing && this.createdPlan) {
      // Reintento: el plan ya existe, solo faltan sus días.
      this.saveCreatedRoutine(this.createdPlan);
      return;
    }
    const request = editing
      ? this.api.patch<TrainingPlan>(`planes-entrenamiento/${editing.id}/`, payload)
      : this.api.post<TrainingPlan>('planes-entrenamiento/', payload);
    request.subscribe({
      next: (plan) => {
        if (!editing && this.createWithRoutine()) {
          this.createdPlan = plan;
          this.plans.update((plans) => [plan, ...plans.filter((item) => item.id !== plan.id)]);
          this.saveCreatedRoutine(plan);
          return;
        }
        this.saving.set(false);
        this.form.controls.cliente.enable();
        this.modalOpen.set(false);
        this.closeBuilder();
        this.toast.success(editing ? 'Plan actualizado' : 'Entrenamiento creado');
        this.load(plan.id);
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

  /** Guarda, día por día, la rutina armada en «Crear entrenamiento». */
  private saveCreatedRoutine(plan: TrainingPlan): void {
    const days = this.daysToSave();
    this.saveDays(plan, days).subscribe({
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(
          `El plan se creó, pero no se pudo guardar el ${this.builderDayInfo().label.toLowerCase()}: ` +
            `${this.describeDayError(error)} Corrígelo y pulsa «Guardar plan» otra vez.`,
        );
      },
      complete: () => {
        this.saving.set(false);
        this.createdPlan = null;
        this.form.controls.cliente.enable();
        this.modalOpen.set(false);
        const totals = this.weekTotals();
        this.closeBuilder();
        this.toast.success(
          'Entrenamiento creado',
          totals.exercises
            ? `${totals.days} ${totals.days === 1 ? 'día' : 'días'} · ${totals.exercises} ejercicios · ${totals.sets} series`
            : 'Puedes agregar ejercicios con «Armar».',
        );
        this.selectedId.set(null);
        this.load(plan.id);
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

  // ----- Editor de la semana (entrenador / administrador) -----

  /** «Armar»: abre toda la semana del plan como borrador, empezando por el día elegido. */
  protected openDayEditor(): void {
    const plan = this.selectedPlan();
    if (!plan) return;
    const week = emptyWeek();
    for (const day of this.days()) {
      const config = plan.rutina?.[day.value];
      week[day.value] = {
        titulo: config?.titulo ?? '',
        musculos: [...(config?.musculos ?? [])],
        rows: day.rows.map((row) => this.rowFromPlan(row)),
      };
    }
    this.startBuilder('edit', week, this.selectedDay());
  }

  private startBuilder(mode: BuilderMode, week: WeekDraft, day: WeekDay): void {
    this.week.set(week);
    this.weekSnapshot = Object.fromEntries(
      WEEK_DAYS.map((item) => [item.value, this.serializeDay(week[item.value])]),
    );
    this.builderDay.set(day);
    this.editorError.set(null);
    this.rowErrors.set({});
    this.musclesOpen.set(false);
    this.pickerOpen.set(false);
    this.builderMode.set(mode);
  }

  private closeBuilder(): void {
    this.builderMode.set('closed');
    this.pickerOpen.set(false);
    this.editorError.set(null);
    this.rowErrors.set({});
  }

  /** «Cancelar»: descarta el borrador (pide confirmación si hubo cambios). */
  protected async cancelDayEditor(): Promise<void> {
    if (this.daySaving() || !(await this.confirmDiscard())) return;
    this.closeBuilder();
  }

  /** Días cuyo borrador cambió desde que se abrió el editor. */
  private changedDays(): WeekDay[] {
    return WEEK_DAYS.map((day) => day.value).filter(
      (day) => this.serializeDay(this.week()[day]) !== this.weekSnapshot[day],
    );
  }

  /** Al crear: los días con algo armado. Al editar: los que cambiaron. */
  private daysToSave(): WeekDay[] {
    if (this.builderMode() === 'create') {
      return WEEK_DAYS.map((day) => day.value).filter((day) => {
        const draft = this.week()[day];
        return draft.rows.length || draft.titulo.trim() || draft.musculos.length;
      }).filter((day) => this.serializeDay(this.week()[day]) !== this.weekSnapshot[day]);
    }
    return this.changedDays();
  }

  private async confirmDiscard(): Promise<boolean> {
    if (this.builderMode() === 'closed' || !this.changedDays().length) return true;
    return this.confirm.confirm({
      title: 'Descartar cambios',
      message: 'Los ejercicios y días que armaste y no guardaste se perderán.',
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

  private serializeDay(day: DayDraft): string {
    return JSON.stringify({
      titulo: day.titulo.trim(),
      musculos: [...day.musculos].sort(),
      ejercicios: this.dayPayload(day),
    });
  }

  private dayPayload(day: DayDraft): TrainingDayExerciseInput[] {
    return day.rows.map((row) => ({
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

  private rowValid(row: DraftRow): boolean {
    return (
      this.inRange(row.series, 'series') &&
      this.inRange(row.repeticiones, 'repeticiones') &&
      this.inRange(row.descanso_segundos, 'descanso_segundos') &&
      (row.peso_kg === '' || Number(row.peso_kg) >= 0)
    );
  }

  private focusFirstInvalidDay(): void {
    const invalid = this.builderTabs().find((tab) => tab.invalid);
    if (invalid) this.selectBuilderDay(invalid.value);
  }

  /** Cambia el día abierto del borrador. */
  private updateOpenDay(change: (day: DayDraft) => DayDraft): void {
    const key = this.builderDay();
    this.week.update((week) => ({ ...week, [key]: change(week[key]) }));
  }

  protected setDayTitle(value: string): void {
    this.updateOpenDay((day) => ({ ...day, titulo: value }));
  }

  protected setDayMuscles(muscles: string[]): void {
    this.updateOpenDay((day) => ({ ...day, musculos: muscles }));
  }

  protected toggleDayMuscle(code: string): void {
    this.updateOpenDay((day) => ({ ...day, musculos: toggleMuscle(day.musculos, code) }));
  }

  protected setNumber(index: number, field: DraftNumberField, raw: string): void {
    const value = raw.trim() === '' ? null : Number(raw);
    this.patchRow(index, { [field]: Number.isNaN(value) ? null : value });
  }

  protected setText(index: number, field: 'peso_kg' | 'observaciones', value: string): void {
    this.patchRow(index, { [field]: value });
  }

  private patchRow(index: number, patch: Partial<DraftRow>): void {
    this.updateOpenDay((day) => ({
      ...day,
      rows: day.rows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
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
    this.updateOpenDay((day) => {
      if (target < 0 || target >= day.rows.length) return day;
      const rows = [...day.rows];
      [rows[index], rows[target]] = [rows[target], rows[index]];
      return { ...day, rows };
    });
    this.rowErrors.set({});
  }

  protected removeRow(index: number): void {
    this.updateOpenDay((day) => ({ ...day, rows: day.rows.filter((_, i) => i !== index) }));
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

  /** Agrega todos los ejercicios marcados al final del día abierto, en el orden en que se marcaron. */
  protected addPicked(): void {
    const byId = new Map(this.exercises().map((exercise) => [exercise.id, exercise]));
    const picked = this.pickerSelected()
      .map((id) => byId.get(id))
      .filter((exercise): exercise is Exercise => !!exercise)
      .slice(0, Math.max(this.pickerRoom(), 0));
    if (!picked.length) return;
    const series = this.inRange(this.pickerSets(), 'series') ? this.pickerSets() : 3;
    const repeticiones = this.inRange(this.pickerReps(), 'repeticiones') ? this.pickerReps() : 10;
    this.updateOpenDay((day) => ({
      ...day,
      rows: [
        ...day.rows,
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
      ],
      // Los músculos de los ejercicios nuevos se marcan en el día (se pueden desmarcar).
      // Solo los del catálogo: un código desconocido no se podría desmarcar y el servidor lo rechazaría.
      musculos: [
        ...new Set([
          ...day.musculos,
          ...picked
            .flatMap((exercise) => exercise.musculos ?? [])
            .filter((code) => !!findMuscle(code) || isGroupCode(code)),
        ]),
      ],
    }));
    this.pickerOpen.set(false);
    this.toast.success(
      picked.length === 1 ? 'Ejercicio agregado' : `${picked.length} ejercicios agregados`,
      `Al ${this.builderDayInfo().label.toLowerCase()}. Ajusta series y repeticiones y pulsa «Guardar plan».`,
    );
  }

  // ----- Guardar -----

  /** «Guardar plan» del editor de un plan existente: guarda todos los días que cambiaron. */
  protected saveDayPlan(): void {
    const plan = this.selectedPlan();
    if (!plan || this.daySaving()) return;
    this.editorError.set(null);
    this.rowErrors.set({});
    if (!this.weekValid()) {
      this.focusFirstInvalidDay();
      this.editorError.set('Revisa las series y repeticiones marcadas en rojo.');
      return;
    }
    const days = this.changedDays();
    if (!days.length) {
      this.closeBuilder();
      this.toast.success('Sin cambios', 'El plan ya estaba guardado así.');
      return;
    }
    this.daySaving.set(true);
    this.saveDays(plan, days).subscribe({
      error: (error: unknown) => {
        this.daySaving.set(false);
        const fields = erroresDelServidor(error);
        const general = ['titulo', 'musculos', 'rutina', 'entrenador', 'general']
          .map((field) => fields[field])
          .filter(Boolean)
          .join(' ');
        this.editorError.set(
          `${this.builderDayInfo().label}: ` +
            (general ||
              (Object.keys(this.rowErrors()).length
                ? 'revisa los ejercicios marcados.'
                : error instanceof ApiError
                  ? error.message
                  : 'no se pudo guardar.')),
        );
      },
      complete: () => {
        this.daySaving.set(false);
        this.closeBuilder();
        const count = days.length;
        this.toast.success(
          'Plan guardado',
          `${count} ${count === 1 ? 'día actualizado' : 'días actualizados'} · ${this.weekTotals().exercises} ejercicios en la semana`,
        );
      },
    });
  }

  /**
   * Guarda los días uno tras otro (cada uno es una transacción en el servidor).
   * Si uno falla, se detiene en ese día y marca sus filas con error.
   */
  private saveDays(plan: TrainingPlan, days: WeekDay[]): Observable<TrainingDaySaveResponse> {
    return from(days).pipe(
      concatMap((day) => {
        const draft = this.week()[day];
        const body = { titulo: draft.titulo.trim(), musculos: draft.musculos, ejercicios: this.dayPayload(draft) };
        return this.api.put<TrainingDaySaveResponse>(`planes-entrenamiento/${plan.id}/dias/${day}/`, body).pipe(
          map((response) => {
            this.weekSnapshot[day] = this.serializeDay(draft);
            this.plans.update((plans) => plans.map((item) => (item.id === response.plan.id ? response.plan : item)));
            if (this.selectedId() === plan.id) {
              this.planExercises.update((rows) => [
                ...rows.filter((row) => row.dia_semana !== day),
                ...response.ejercicios,
              ]);
            }
            return response;
          }),
          // Si este día falla, el editor queda abierto en él con sus errores.
          catchError((error: unknown) => {
            this.selectBuilderDay(day);
            this.rowErrors.set(this.rowErrorsFrom(error));
            return throwError(() => error);
          }),
        );
      }),
    );
  }

  private describeDayError(error: unknown): string {
    const fields = erroresDelServidor(error);
    const messages = Object.values(fields).filter(Boolean).join(' ');
    return messages || (error instanceof ApiError ? error.message : 'error desconocido.');
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
