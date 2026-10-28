import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { ClientProfile, PaginatedResponse, Role } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import { dateInput, formatDate, humanize } from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { PaginationComponent } from '../../shared/pagination.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-clients-page',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    IconComponent,
    AvatarComponent,
    PageHeaderComponent,
    PaginationComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './clients.page.html',
  styleUrl: './clients.page.css',
})
export class ClientsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);

  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 25;
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<ClientProfile | null>(null);
  private readonly roles = signal<Role[]>([]);

  protected readonly search = this.formBuilder.nonNullable.control('');
  protected readonly activeFilter = this.formBuilder.nonNullable.control('');
  protected readonly documentFilter = this.formBuilder.nonNullable.control('');

  protected readonly form = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required]],
    correo: ['', [Validators.required, Validators.email]],
    telefono: [''],
    contrasena: [''],
    tipo_documento: [''],
    numero_documento: [''],
    fecha_nacimiento: [''],
    objetivo: [''],
    peso_kg: [''],
    estatura_cm: [''],
    is_active: [true],
  });

  ngOnInit(): void {
    this.api.getAll<Role>('roles/', { is_active: true }).subscribe({
      next: (roles) => this.roles.set(roles),
      error: () => this.roles.set([]),
    });
    this.load();
    this.search.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.page.set(1);
        this.load();
      });
    for (const control of [this.activeFilter, this.documentFilter]) {
      control.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
        this.page.set(1);
        this.load();
      });
    }
    if (this.route.snapshot.queryParamMap.get('nuevo') === '1' && this.canCreate()) {
      this.openCreate();
    }
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .get<PaginatedResponse<ClientProfile>>('clientes/', {
        page: this.page(),
        search: this.search.value.trim(),
        is_active: this.activeFilter.value || null,
        tipo_documento: this.documentFilter.value || null,
      })
      .subscribe({
        next: (response) => {
          this.clients.set(response.results);
          this.count.set(response.count);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar los clientes.');
        },
      });
  }

  protected changePage(page: number): void {
    this.page.set(page);
    this.load();
  }

  protected canCreate(): boolean {
    return (
      this.auth.isAdmin() &&
      this.auth.hasPermission('clientes:create') &&
      this.auth.hasPermission('usuarios:create')
    );
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      nombre: '',
      correo: '',
      telefono: '',
      contrasena: '',
      tipo_documento: '',
      numero_documento: '',
      fecha_nacimiento: '',
      objetivo: '',
      peso_kg: '',
      estatura_cm: '',
      is_active: true,
    });
    this.form.controls.nombre.enable();
    this.form.controls.correo.enable();
    this.form.controls.telefono.enable();
    this.form.controls.contrasena.setValidators([Validators.required, Validators.minLength(8)]);
    this.form.controls.contrasena.updateValueAndValidity();
    this.modalOpen.set(true);
  }

  protected openEdit(client: ClientProfile): void {
    this.editing.set(client);
    this.formError.set(null);
    this.form.reset({
      nombre: client.usuario_detalle.nombre,
      correo: client.usuario_detalle.correo,
      telefono: client.usuario_detalle.telefono ?? '',
      contrasena: '',
      tipo_documento: client.tipo_documento ?? '',
      numero_documento: client.numero_documento ?? '',
      fecha_nacimiento: dateInput(client.fecha_nacimiento),
      objetivo: client.objetivo ?? '',
      peso_kg: client.peso_kg ?? '',
      estatura_cm: client.estatura_cm ?? '',
      is_active: client.is_active,
    });
    this.form.controls.nombre.disable();
    this.form.controls.correo.disable();
    this.form.controls.telefono.disable();
    this.form.controls.contrasena.clearValidators();
    this.form.controls.contrasena.updateValueAndValidity();
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
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
    const profile = {
      tipo_documento: raw.tipo_documento || null,
      numero_documento: raw.numero_documento.trim() || null,
      fecha_nacimiento: raw.fecha_nacimiento || null,
      objetivo: raw.objetivo.trim() || null,
      peso_kg: raw.peso_kg || null,
      estatura_cm: raw.estatura_cm || null,
      is_active: raw.is_active,
    };
    this.saving.set(true);
    const editing = this.editing();

    if (editing) {
      this.api.patch<ClientProfile>(`clientes/${editing.usuario}/`, profile).subscribe({
        next: () => this.saved(editing),
        error: (error: unknown) => this.failed(error),
      });
      return;
    }

    const clientRole = this.roles().find((role) => role.nombre === 'cliente');
    if (!clientRole) {
      this.saving.set(false);
      this.formError.set('No se encontró el rol de cliente. Contacta al administrador.');
      return;
    }
    const payload = {
      rol: clientRole.id,
      nombre: raw.nombre.trim(),
      correo: raw.correo.trim(),
      telefono: raw.telefono.trim() || null,
      contrasena: raw.contrasena,
      is_active: true,
      perfil: profile,
    };
    this.api.post('usuarios/', payload).subscribe({
      next: () => this.saved(null),
      error: (error: unknown) => this.failed(error),
    });
  }

  protected async remove(client: ClientProfile): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar cliente',
      message: `Se desactivará el perfil de ${client.usuario_detalle.nombre}. La cuenta de usuario se conserva.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`clientes/${client.usuario}/`).subscribe({
      next: () => {
        this.toast.success('Cliente eliminado');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected formatDate = formatDate;
  protected humanize = humanize;

  private saved(editing: ClientProfile | null): void {
    this.saving.set(false);
    this.modalOpen.set(false);
    this.toast.success(editing ? 'Cliente actualizado' : 'Cliente creado');
    this.load();
  }

  private failed(error: unknown): void {
    this.saving.set(false);
    this.formError.set(
      error instanceof ApiError ? error.fieldErrors()['correo'] || error.message : 'No se pudo guardar el cliente.',
    );
  }
}
