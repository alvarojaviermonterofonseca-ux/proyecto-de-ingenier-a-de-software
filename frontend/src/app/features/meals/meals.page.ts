import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Meal, NutritionPlan } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { MEAL_TYPES, formatTime, humanize } from '../../core/utils/format';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';

@Component({
  selector: 'app-meals-page',
  standalone: true,
  imports: [
    KeyValuePipe,
    RouterLink,
    ReactiveFormsModule,
    IconComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './meals.page.html',
  styleUrl: './meals.page.css',
})
export class MealsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);

  protected readonly meals = signal<Meal[]>([]);
  protected readonly plans = signal<NutritionPlan[]>([]);
  protected readonly planFilter = signal<number | null>(null);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<Meal | null>(null);
  protected readonly mealTypes = MEAL_TYPES;

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    if (!query) return this.meals();
    return this.meals().filter(
      (meal) =>
        meal.nombre.toLowerCase().includes(query) ||
        (meal.descripcion ?? '').toLowerCase().includes(query),
    );
  });

  protected readonly selectedPlan = computed(
    () => this.plans().find((plan) => plan.id === this.planFilter()) ?? null,
  );

  protected readonly form = this.formBuilder.nonNullable.group({
    plan_alimentacion: [0, [Validators.required]],
    nombre: ['', [Validators.required]],
    tipo: ['desayuno', [Validators.required]],
    hora_sugerida: [''],
    descripcion: [''],
  });

  ngOnInit(): void {
    const planId = Number(this.route.snapshot.queryParamMap.get('plan'));
    if (planId > 0) {
      this.planFilter.set(planId);
    }
    this.loadPlans();
    this.load();
  }

  protected loadPlans(): void {
    this.api.getAll<NutritionPlan>('planes-alimentacion/').subscribe({
      next: (plans) => this.plans.set(plans),
      error: () => this.plans.set([]),
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .getAll<Meal>('comidas/', { plan_alimentacion: this.planFilter() })
      .subscribe({
        next: (meals) => {
          this.meals.set(
            meals.sort((a, b) => (a.hora_sugerida ?? '').localeCompare(b.hora_sugerida ?? '')),
          );
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar las comidas.');
        },
      });
  }

  protected selectPlan(value: string): void {
    this.planFilter.set(value ? Number(value) : null);
    this.load();
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      plan_alimentacion: this.planFilter() ?? 0,
      nombre: '',
      tipo: 'desayuno',
      hora_sugerida: '',
      descripcion: '',
    });
    this.form.controls.plan_alimentacion.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(meal: Meal): void {
    this.editing.set(meal);
    this.formError.set(null);
    this.form.reset({
      plan_alimentacion: meal.plan_alimentacion,
      nombre: meal.nombre,
      tipo: meal.tipo,
      hora_sugerida: meal.hora_sugerida ?? '',
      descripcion: meal.descripcion ?? '',
    });
    this.form.controls.plan_alimentacion.disable();
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.form.controls.plan_alimentacion.enable();
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
      nombre: raw.nombre.trim(),
      tipo: raw.tipo,
      hora_sugerida: raw.hora_sugerida || null,
      descripcion: raw.descripcion.trim() || null,
    };
    if (!editing) payload['plan_alimentacion'] = raw.plan_alimentacion;
    this.saving.set(true);
    const request = editing
      ? this.api.patch<Meal>(`comidas/${editing.id}/`, payload)
      : this.api.post<Meal>('comidas/', payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.form.controls.plan_alimentacion.enable();
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Comida actualizada' : 'Comida agregada');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar la comida.');
      },
    });
  }

  protected async remove(meal: Meal): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar comida',
      message: `Se eliminará ${meal.nombre} del plan de alimentación.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`comidas/${meal.id}/`).subscribe({
      next: () => {
        this.toast.success('Comida eliminada');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected planName(planId: number): string {
    return this.plans().find((plan) => plan.id === planId)?.nombre ?? `Plan #${planId}`;
  }

  protected typeLabel(type: string): string {
    return MEAL_TYPES[type] ?? humanize(type);
  }

  protected formatTime = formatTime;
  protected humanize = humanize;
}
