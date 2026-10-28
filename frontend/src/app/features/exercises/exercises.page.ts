import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Exercise } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { humanize } from '../../core/utils/format';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-exercises-page',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    IconComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './exercises.page.html',
  styleUrl: './exercises.page.css',
})
export class ExercisesPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly exercises = signal<Exercise[]>([]);
  protected readonly search = signal('');
  protected readonly groupFilter = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<Exercise | null>(null);

  protected readonly groups = computed(() =>
    [...new Set(this.exercises().map((exercise) => exercise.grupo_muscular).filter(Boolean))].sort() as string[],
  );

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const group = this.groupFilter();
    return this.exercises().filter((exercise) => {
      if (group && exercise.grupo_muscular !== group) return false;
      if (!query) return true;
      return (
        exercise.nombre.toLowerCase().includes(query) ||
        (exercise.descripcion ?? '').toLowerCase().includes(query) ||
        (exercise.grupo_muscular ?? '').toLowerCase().includes(query)
      );
    });
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required]],
    grupo_muscular: [''],
    descripcion: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Exercise>('ejercicios/').subscribe({
      next: (exercises) => {
        this.exercises.set(exercises);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los ejercicios.');
      },
    });
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({ nombre: '', grupo_muscular: '', descripcion: '' });
    this.modalOpen.set(true);
  }

  protected openEdit(exercise: Exercise): void {
    this.editing.set(exercise);
    this.formError.set(null);
    this.form.reset({
      nombre: exercise.nombre,
      grupo_muscular: exercise.grupo_muscular ?? '',
      descripcion: exercise.descripcion ?? '',
    });
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) this.modalOpen.set(false);
  }

  protected save(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const payload = {
      nombre: raw.nombre.trim(),
      grupo_muscular: raw.grupo_muscular.trim() || null,
      descripcion: raw.descripcion.trim() || null,
    };
    const editing = this.editing();
    this.saving.set(true);
    const request = editing
      ? this.api.patch<Exercise>(`ejercicios/${editing.id}/`, payload)
      : this.api.post<Exercise>('ejercicios/', payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Ejercicio actualizado' : 'Ejercicio creado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar el ejercicio.');
      },
    });
  }

  protected async remove(exercise: Exercise): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar ejercicio',
      message: `Se eliminará ${exercise.nombre} del catálogo. Los planes existentes conservan su historial.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`ejercicios/${exercise.id}/`).subscribe({
      next: () => {
        this.toast.success('Ejercicio eliminado');
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

  protected humanize = humanize;
}
