import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { ClientProfile, NutritionPlan, TrainerProfile } from '../../core/api/api.models';
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
  selector: 'app-nutrition-plans-page',
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
  templateUrl: './nutrition-plans.page.html',
  styleUrl: './nutrition-plans.page.css',
})
export class NutritionPlansPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly plans = signal<NutritionPlan[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly trainers = signal<TrainerProfile[]>([]);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<NutritionPlan | null>(null);

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

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required]],
    responsable: [0, [Validators.required]],
    nombre: ['', [Validators.required]],
    objetivo: ['', [Validators.required]],
    calorias_objetivo: [''],
    fecha_inicio: [new Date().toISOString().slice(0, 10), [Validators.required]],
    fecha_fin: [''],
    activo: [true],
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
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<NutritionPlan>('planes-alimentacion/').subscribe({
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
      responsable: 0,
      nombre: '',
      objetivo: '',
      calorias_objetivo: '',
      fecha_inicio: new Date().toISOString().slice(0, 10),
      fecha_fin: '',
      activo: true,
      observaciones: '',
    });
    this.form.controls.cliente.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(plan: NutritionPlan): void {
    this.editing.set(plan);
    this.formError.set(null);
    this.form.reset({
      cliente: plan.cliente,
      responsable: plan.responsable,
      nombre: plan.nombre,
      objetivo: plan.objetivo,
      calorias_objetivo: plan.calorias_objetivo ?? '',
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
      responsable: raw.responsable,
      nombre: raw.nombre.trim(),
      objetivo: raw.objetivo.trim(),
      calorias_objetivo: raw.calorias_objetivo || null,
      fecha_inicio: raw.fecha_inicio,
      fecha_fin: raw.fecha_fin || null,
      activo: raw.activo,
      observaciones: raw.observaciones.trim() || null,
    };
    if (!editing) payload['cliente'] = raw.cliente;
    this.saving.set(true);
    const request = editing
      ? this.api.patch<NutritionPlan>(`planes-alimentacion/${editing.id}/`, payload)
      : this.api.post<NutritionPlan>('planes-alimentacion/', payload);
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

  protected async remove(plan: NutritionPlan): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar plan',
      message: `Se eliminará el plan "${plan.nombre}" de ${plan.cliente_detalle.nombre}.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`planes-alimentacion/${plan.id}/`).subscribe({
      next: () => {
        this.toast.success('Plan eliminado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected formatDate = formatDate;
}
