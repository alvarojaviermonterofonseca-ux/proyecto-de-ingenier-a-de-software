import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Exercise } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { erroresDelServidor } from '../../core/forms/field-errors';
import { ExerciseImagesService } from '../../core/training/exercise-images.service';
import { BODY_REGIONS, MUSCLES, apiPath, matchesMuscle, muscleLabel } from '../../core/training/muscles';
import { humanize } from '../../core/utils/format';
import { ExerciseThumbComponent } from '../../shared/exercise-thumb.component';
import { MusclePickerComponent } from '../../shared/muscle-picker.component';
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
    ExerciseThumbComponent,
    MusclePickerComponent,
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
  protected readonly muscleFilter = signal('');
  protected readonly selectedMuscles = signal<string[]>([]);
  /** Archivo elegido para subir y su vista previa local. */
  protected readonly imageFile = signal<File | null>(null);
  protected readonly imagePreview = signal<string | null>(null);
  protected readonly removeImage = signal(false);
  protected readonly imageError = signal<string | null>(null);
  protected readonly serverErrors = signal<Record<string, string>>({});
  protected readonly muscleRegions = BODY_REGIONS.map((name) => ({
    name,
    muscles: MUSCLES.filter((muscle) => muscle.region === name),
  }));
  protected readonly muscleLabel = muscleLabel;
  protected readonly apiPath = apiPath;
  private readonly images = inject(ExerciseImagesService);

  /** Imagen actual del ejercicio en edición (ya guardada en el servidor). */
  protected readonly currentImage = computed(() => {
    const exercise = this.editing();
    if (!exercise?.imagen_url || this.removeImage()) return null;
    const path = apiPath(exercise.imagen_url);
    return path ? this.images.url(`${path}#${exercise.updated_at}`) : null;
  });

  protected readonly groups = computed(() =>
    [...new Set(this.exercises().map((exercise) => exercise.grupo_muscular).filter(Boolean))].sort() as string[],
  );

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const group = this.groupFilter();
    const muscle = this.muscleFilter();
    return this.exercises().filter((exercise) => {
      if (group && exercise.grupo_muscular !== group) return false;
      if (muscle && !matchesMuscle(exercise.musculos, muscle)) return false;
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

  private resetImage(): void {
    const preview = this.imagePreview();
    if (preview) URL.revokeObjectURL(preview);
    this.imageFile.set(null);
    this.imagePreview.set(null);
    this.removeImage.set(false);
    this.imageError.set(null);
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.serverErrors.set({});
    this.resetImage();
    this.selectedMuscles.set([]);
    this.form.reset({ nombre: '', grupo_muscular: '', descripcion: '' });
    this.modalOpen.set(true);
  }

  protected onImageSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) return;
    this.imageError.set(null);
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      this.imageError.set('Usa una imagen JPG, PNG o WebP.');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      this.imageError.set('La imagen no puede pesar más de 5 MB.');
      return;
    }
    const preview = this.imagePreview();
    if (preview) URL.revokeObjectURL(preview);
    this.imageFile.set(file);
    this.imagePreview.set(URL.createObjectURL(file));
    this.removeImage.set(false);
  }

  protected onImageDropped(event: DragEvent): void {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    this.onImageSelected({ target: { files: [file], value: '' } } as unknown as Event);
  }

  protected clearImage(): void {
    const preview = this.imagePreview();
    if (preview) URL.revokeObjectURL(preview);
    this.imageFile.set(null);
    this.imagePreview.set(null);
    this.removeImage.set(Boolean(this.editing()?.imagen_url));
  }

  protected openEdit(exercise: Exercise): void {
    this.resetImage();
    this.editing.set(exercise);
    this.formError.set(null);
    this.serverErrors.set({});
    this.selectedMuscles.set([...(exercise.musculos ?? [])]);
    const path = apiPath(exercise.imagen_url);
    if (path) this.images.load(`${path}#${exercise.updated_at}`, path);
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
    // Multipart para poder adjuntar la imagen junto con los datos.
    const data = new FormData();
    data.append('nombre', raw.nombre.trim());
    data.append('grupo_muscular', raw.grupo_muscular.trim());
    data.append('descripcion', raw.descripcion.trim());
    data.append('musculos', JSON.stringify(this.selectedMuscles()));
    const file = this.imageFile();
    if (file) data.append('imagen', file);
    else if (this.removeImage()) data.append('quitar_imagen', 'true');
    const editing = this.editing();
    this.saving.set(true);
    this.serverErrors.set({});
    const request = editing
      ? this.api.uploadPatch<Exercise>(`ejercicios/${editing.id}/`, data)
      : this.api.upload<Exercise>('ejercicios/', data);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.modalOpen.set(false);
        this.resetImage();
        this.toast.success(editing ? 'Ejercicio actualizado' : 'Ejercicio creado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        const campos = erroresDelServidor(error);
        this.serverErrors.set(campos);
        this.formError.set(
          Object.keys(campos).length
            ? 'Revisa los campos marcados.'
            : error instanceof ApiError
              ? error.message
              : 'No se pudo guardar el ejercicio.',
        );
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
