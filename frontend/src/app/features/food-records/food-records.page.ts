import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { ClientProfile, FoodRecord, Meal, NutritionPlan } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { dateTimeInput, formatDateTime } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

type VerificationFilter = 'all' | 'pending' | 'verified';

@Component({
  selector: 'app-food-records-page',
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
  templateUrl: './food-records.page.html',
  styleUrl: './food-records.page.css',
})
export class FoodRecordsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);

  protected readonly records = signal<FoodRecord[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly meals = signal<Meal[]>([]);
  protected readonly plans = signal<NutritionPlan[]>([]);
  protected readonly search = signal('');
  protected readonly verification = signal<VerificationFilter>('all');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<FoodRecord | null>(null);
  protected readonly formClient = signal(0);
  protected readonly selectedPhoto = signal<File | null>(null);
  protected readonly localPhotoPreview = signal<string | null>(null);
  protected readonly existingPhotoUrl = signal<string | null>(null);
  protected readonly photoUrls = signal<Record<number, string>>({});
  protected readonly cameraOpen = signal(false);
  protected readonly cameraError = signal<string | null>(null);

  private readonly cameraVideo = viewChild<ElementRef<HTMLVideoElement>>('cameraVideo');
  private stream: MediaStream | null = null;
  private readonly photoObjectUrls = new Map<number, string>();

  protected readonly isClient = computed(() => this.auth.roleName() === 'cliente');
  protected readonly canReview = computed(
    () => !this.isClient() && this.auth.hasPermission('registros-comida:edit'),
  );

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const verification = this.verification();
    return this.records().filter((record) => {
      if (verification === 'pending' && record.verificado) return false;
      if (verification === 'verified' && !record.verificado) return false;
      if (!query) return true;
      return (
        record.cliente_detalle.nombre.toLowerCase().includes(query) ||
        (record.comida_nombre ?? '').toLowerCase().includes(query) ||
        (record.observaciones ?? '').toLowerCase().includes(query)
      );
    });
  });

  protected readonly availableMeals = computed(() => {
    const clientId = this.formClient();
    if (!clientId) return [];
    const planIds = new Set(
      this.plans().filter((plan) => plan.cliente === clientId).map((plan) => plan.id),
    );
    return this.meals().filter((meal) => planIds.has(meal.plan_alimentacion));
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required]],
    comida: [0],
    registrado_at: [dateTimeInput(new Date().toISOString()), [Validators.required]],
    verificado: [false],
    calificacion: [''],
    observaciones: [''],
  });

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.stopCamera();
      this.revokeLocalPreview();
      this.revokePhotos();
    });
  }

  ngOnInit(): void {
    this.load();
    this.api.getAll<ClientProfile>('clientes/').subscribe({
      next: (clients) => this.clients.set(clients),
      error: () => this.clients.set([]),
    });
    this.api.getAll<NutritionPlan>('planes-alimentacion/').subscribe({
      next: (plans) => this.plans.set(plans),
      error: () => this.plans.set([]),
    });
    this.api.getAll<Meal>('comidas/').subscribe({
      next: (meals) => this.meals.set(meals),
      error: () => this.meals.set([]),
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.revokePhotos();
    this.photoUrls.set({});
    this.api.getAll<FoodRecord>('registros-comida/').subscribe({
      next: (records) => {
        this.records.set(
          records.sort(
            (a, b) => new Date(b.registrado_at).getTime() - new Date(a.registrado_at).getTime(),
          ),
        );
        this.loading.set(false);
        this.loadPhotos(records);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los registros.');
      },
    });
  }

  protected openCreate(): void {
    const current = this.auth.user();
    this.editing.set(null);
    this.formError.set(null);
    this.selectedPhoto.set(null);
    this.revokeLocalPreview();
    this.stopCamera();
    this.cameraError.set(null);
    this.existingPhotoUrl.set(null);
    const defaultClient = this.isClient() && current ? current.id : 0;
    this.formClient.set(defaultClient);
    this.form.reset({
      cliente: defaultClient,
      comida: 0,
      registrado_at: dateTimeInput(new Date().toISOString()),
      verificado: false,
      calificacion: '',
      observaciones: '',
    });
    this.form.controls.cliente.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(record: FoodRecord): void {
    this.editing.set(record);
    this.formError.set(null);
    this.selectedPhoto.set(null);
    this.revokeLocalPreview();
    this.stopCamera();
    this.cameraError.set(null);
    this.formClient.set(record.cliente);
    this.form.reset({
      cliente: record.cliente,
      comida: record.comida ?? 0,
      registrado_at: dateTimeInput(record.registrado_at),
      verificado: record.verificado,
      calificacion: record.calificacion ?? '',
      observaciones: record.observaciones ?? '',
    });
    this.form.controls.cliente.disable();
    this.existingPhotoUrl.set(this.photoUrls()[record.id] ?? null);
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.stopCamera();
      this.cameraError.set(null);
      this.form.controls.cliente.enable();
      this.modalOpen.set(false);
      this.selectedPhoto.set(null);
      this.revokeLocalPreview();
      this.existingPhotoUrl.set(null);
    }
  }

  protected updateFormClient(value: string): void {
    const clientId = Number(value);
    this.formClient.set(clientId);
    const meal = this.form.controls.comida.value;
    if (meal && !this.availableMeals().some((item) => item.id === meal)) {
      this.form.controls.comida.setValue(0);
    }
  }

  protected onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.setPhoto(input.files?.[0] ?? null);
  }

  protected clearPhoto(input: HTMLInputElement): void {
    input.value = '';
    this.setPhoto(null);
  }

  /** Abre la cámara del dispositivo (trasera si existe) con vista previa en vivo. */
  protected async startCamera(): Promise<void> {
    this.cameraError.set(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      this.cameraError.set(
        'Este navegador no permite usar la cámara aquí. Usa "Elegir archivo" o abre la app en localhost/HTTPS.',
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 960 },
        },
        audio: false,
      });
      // El modal pudo cerrarse mientras el navegador pedía permiso.
      if (!this.modalOpen()) {
        for (const track of stream.getTracks()) track.stop();
        return;
      }
      this.stopCamera();
      this.stream = stream;
      this.cameraOpen.set(true);
      // El <video> aparece en el siguiente ciclo; se enlaza cuando ya existe.
      setTimeout(() => {
        const video = this.cameraVideo()?.nativeElement;
        if (!video) return;
        video.srcObject = stream;
        void video.play().catch(() => undefined);
      });
    } catch {
      this.cameraError.set(
        'No se pudo abrir la cámara. Revisa el permiso del navegador para este sitio o usa "Elegir archivo".',
      );
    }
  }

  /** Toma una foto del video en vivo y la deja lista para subirla. */
  protected capturePhoto(): void {
    const video = this.cameraVideo()?.nativeElement;
    if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
      this.cameraError.set('La cámara aún se está preparando. Intenta de nuevo.');
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) {
      this.cameraError.set('No se pudo procesar la imagen de la cámara.');
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          this.cameraError.set('No se pudo capturar la foto. Intenta de nuevo.');
          return;
        }
        const file = new File([blob], `comida-${Date.now()}.jpg`, {
          type: 'image/jpeg',
        });
        this.setPhoto(file);
        this.stopCamera();
      },
      'image/jpeg',
      0.9,
    );
  }

  protected stopCamera(): void {
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
    const video = this.cameraVideo()?.nativeElement;
    if (video) video.srcObject = null;
    this.cameraOpen.set(false);
  }

  private setPhoto(file: File | null): void {
    this.revokeLocalPreview();
    this.selectedPhoto.set(file);
    this.localPhotoPreview.set(file ? URL.createObjectURL(file) : null);
    if (file) this.cameraError.set(null);
  }

  protected save(): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const editing = this.editing();
    const formData = new FormData();
    if (!editing) formData.append('cliente', String(raw.cliente));
    if (raw.comida) formData.append('comida', String(raw.comida));
    if (raw.registrado_at) {
      formData.append('registrado_at', new Date(raw.registrado_at).toISOString());
    }
    if (this.canReview()) {
      formData.append('verificado', String(raw.verificado));
      if (raw.calificacion !== '') formData.append('calificacion', raw.calificacion);
    }
    formData.append('observaciones', raw.observaciones.trim());

    const photo = this.selectedPhoto();
    if (photo) formData.append('foto', photo, photo.name);

    this.saving.set(true);
    const request = editing
      ? this.api.uploadPatch<FoodRecord>(`registros-comida/${editing.id}/`, formData)
      : this.api.upload<FoodRecord>('registros-comida/', formData);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.stopCamera();
        this.form.controls.cliente.enable();
        this.modalOpen.set(false);
        this.selectedPhoto.set(null);
        this.revokeLocalPreview();
        this.toast.success(editing ? 'Registro actualizado' : 'Registro creado');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar el registro.');
      },
    });
  }

  protected async remove(record: FoodRecord): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar registro',
      message: `Se eliminará el registro de ${record.cliente_detalle.nombre}.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`registros-comida/${record.id}/`).subscribe({
      next: () => {
        this.toast.success('Registro eliminado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected photoFor(recordId: number): string | null {
    return this.photoUrls()[recordId] ?? null;
  }

  protected setVerification(value: string): void {
    this.verification.set(value as VerificationFilter);
  }

  protected formatDateTime = formatDateTime;

  private loadPhotos(records: readonly FoodRecord[]): void {
    for (const record of records) {
      if (!record.foto_url || this.photoObjectUrls.has(record.id)) continue;
      this.api.blob(`registros-comida/${record.id}/foto/`).subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          this.photoObjectUrls.set(record.id, url);
          this.photoUrls.update((urls) => ({ ...urls, [record.id]: url }));
        },
        error: () => {
          // La foto puede haber sido eliminada; la tarjeta se muestra sin imagen.
        },
      });
    }
  }

  private revokePhotos(): void {
    for (const url of this.photoObjectUrls.values()) URL.revokeObjectURL(url);
    this.photoObjectUrls.clear();
  }

  private revokeLocalPreview(): void {
    const preview = this.localPhotoPreview();
    if (preview) URL.revokeObjectURL(preview);
    this.localPhotoPreview.set(null);
  }
}
