import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Attendance, ClientProfile } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';

interface CheckInResponse {
  creado?: boolean;
  mensaje: string;
  asistencia: Attendance;
}
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import {
  ATTENDANCE_METHODS,
  dateTimeInput,
  formatDate,
  formatDateTime,
  formatTime,
  humanize,
  toIso,
} from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

@Component({
  selector: 'app-attendance-page',
  standalone: true,
  imports: [
    KeyValuePipe,
    ReactiveFormsModule,
    IconComponent,
    AvatarComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
    ModalComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './attendance.page.html',
  styleUrl: './attendance.page.css',
})
export class AttendancePage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);

  protected readonly records = signal<Attendance[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly search = signal('');
  protected readonly statusFilter = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<Attendance | null>(null);
  protected readonly methods = ATTENDANCE_METHODS;

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const status = this.statusFilter();
    return this.records().filter((record) => {
      if (status === 'open' && record.salida_at) return false;
      if (status === 'closed' && !record.salida_at) return false;
      if (!query) return true;
      return (
        record.cliente_detalle.nombre.toLowerCase().includes(query) ||
        record.cliente_detalle.correo.toLowerCase().includes(query)
      );
    });
  });

  protected readonly stats = computed(() => {
    const today = new Date().toDateString();
    const records = this.records();
    return {
      today: records.filter((record) => new Date(record.entrada_at).toDateString() === today).length,
      open: records.filter((record) => !record.salida_at).length,
      average: this.averageMinutes(records),
    };
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    cliente: [0, [Validators.required]],
    metodo_entrada: ['manual', [Validators.required]],
    entrada_at: [dateTimeInput(new Date().toISOString()), [Validators.required]],
    salida_at: [''],
    identificador_evento: [''],
  });

  protected readonly selectedClientId = signal<number>(0);

  protected readonly selectedClientOpenAttendance = computed(() => {
    const clientId = this.selectedClientId();
    if (!clientId) return null;
    return this.records().find((r) => r.cliente === clientId && !r.salida_at) ?? null;
  });

  protected readonly checking = signal(false);

  protected readonly myOpenAttendance = computed(() => {
    const user = this.auth.user();
    if (!user) return null;
    return (
      this.records().find(
        (r) => (r.cliente === user.id || r.cliente_detalle?.correo === user.correo) && !r.salida_at,
      ) ?? null
    );
  });

  ngOnInit(): void {
    this.form.controls.cliente.valueChanges.subscribe((val) => {
      this.selectedClientId.set(Number(val) || 0);
    });
    this.load();
    this.api.getAll<ClientProfile>('clientes/', { is_active: true }).subscribe({
      next: (clients) => {
        this.clients.set(clients);
        if (clients.length > 0 && (!this.form.controls.cliente.value || this.form.controls.cliente.value === 0)) {
          const currentUserId = this.auth.user()?.id;
          const match = clients.find((c) => c.usuario === currentUserId);
          const chosen = match ? match.usuario : clients[0].usuario;
          this.form.controls.cliente.setValue(chosen);
          this.selectedClientId.set(chosen);
        }
      },
      error: () => this.clients.set([]),
    });
    if (
      this.route.snapshot.queryParamMap.get('nuevo') === '1' &&
      this.auth.hasPermission('asistencias:create')
    ) {
      this.openCreate();
    }
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Attendance>('asistencias/').subscribe({
      next: (records) => {
        this.records.set(
          records.sort(
            (a, b) => new Date(b.entrada_at).getTime() - new Date(a.entrada_at).getTime(),
          ),
        );
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar las asistencias.');
      },
    });
  }

  protected updateSearch(value: string): void {
    this.search.set(value);
  }

  protected updateStatus(value: string): void {
    this.statusFilter.set(value);
  }

  protected openCreate(): void {
    this.editing.set(null);
    this.formError.set(null);

    const currentUserId = this.auth.user()?.id;
    const clientMatch = this.clients().find((c) => c.usuario === currentUserId);
    const defaultClient = clientMatch ? clientMatch.usuario : (this.clients()[0]?.usuario ?? 0);

    this.form.reset({
      cliente: defaultClient,
      metodo_entrada: 'manual',
      entrada_at: dateTimeInput(new Date().toISOString()),
      salida_at: '',
      identificador_evento: `REG-${Date.now().toString().slice(-6)}`,
    });
    this.selectedClientId.set(defaultClient);
    this.form.controls.cliente.enable();
    this.form.controls.metodo_entrada.enable();
    this.modalOpen.set(true);
  }

  protected openEdit(record: Attendance): void {
    this.editing.set(record);
    this.formError.set(null);
    this.form.reset({
      cliente: record.cliente,
      metodo_entrada: record.metodo_entrada,
      entrada_at: dateTimeInput(record.entrada_at),
      salida_at: record.salida_at ? dateTimeInput(record.salida_at) : dateTimeInput(new Date().toISOString()),
      identificador_evento: record.identificador_evento ?? '',
    });
    this.selectedClientId.set(record.cliente);
    this.form.controls.cliente.disable();
    this.form.controls.metodo_entrada.disable();
    this.modalOpen.set(true);
  }

  protected saveOrCheckout(): void {
    const openRecord = !this.editing() ? this.selectedClientOpenAttendance() : null;
    if (openRecord) {
      this.checkout(openRecord);
      this.closeModal();
      return;
    }
    this.save();
  }

  protected setCurrentEntrada(): void {
    this.form.controls.entrada_at.setValue(dateTimeInput(new Date().toISOString()));
  }

  protected setCurrentSalida(): void {
    this.form.controls.salida_at.setValue(dateTimeInput(new Date().toISOString()));
  }

  protected setSalidaOffset(hours: number): void {
    const entradaVal = this.form.controls.entrada_at.value;
    const baseDate = entradaVal ? new Date(entradaVal) : new Date();
    baseDate.setHours(baseDate.getHours() + hours);
    this.form.controls.salida_at.setValue(dateTimeInput(baseDate.toISOString()));
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.form.controls.cliente.enable();
      this.form.controls.metodo_entrada.enable();
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
      entrada_at: toIso(raw.entrada_at),
      salida_at: toIso(raw.salida_at),
    };
    if (!editing) {
      payload['cliente'] = raw.cliente;
      payload['metodo_entrada'] = raw.metodo_entrada;
      if (raw.identificador_evento.trim()) {
        payload['identificador_evento'] = raw.identificador_evento.trim();
      }
    }
    if (editing) {
      delete payload['entrada_at'];
      payload['entrada_at'] = toIso(raw.entrada_at);
    }
    this.saving.set(true);
    const request = editing
      ? this.api.patch<Attendance>(`asistencias/${editing.id}/`, payload)
      : this.api.post<Attendance>('asistencias/', payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.form.controls.cliente.enable();
        this.form.controls.metodo_entrada.enable();
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Asistencia actualizada' : 'Entrada registrada');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(error instanceof ApiError ? error.message : 'No se pudo guardar la asistencia.');
      },
    });
  }

  protected checkout(record: Attendance): void {
    if (this.checking()) return;
    this.checking.set(true);

    const user = this.auth.user();
    const isMine = user?.id === record.cliente || user?.correo === record.cliente_detalle?.correo;
    if (isMine || this.auth.roleName() === 'cliente') {
      this.api.post<CheckInResponse>('asistencias/registrar-salida/', {}).subscribe({
        next: (res) => {
          this.checking.set(false);
          const hora = res.asistencia.salida_at ? this.formatTime(res.asistencia.salida_at) : '';
          this.toast.success('Salida registrada', `Visita cerrada a las ${hora}`);
          this.load();
        },
        error: (error: unknown) => {
          this.checking.set(false);
          this.toast.error(
            'No se pudo registrar la salida',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
      return;
    }

    this.api
      .patch<Attendance>(`asistencias/${record.id}/`, { salida_at: new Date().toISOString() })
      .subscribe({
        next: () => {
          this.checking.set(false);
          this.toast.success('Salida registrada', record.cliente_detalle.nombre);
          this.load();
        },
        error: (error: unknown) => {
          this.checking.set(false);
          this.toast.error(
            'No se pudo registrar la salida',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
  }

  protected toggleQuickAttendance(): void {
    if (this.checking()) return;
    const openRecord = this.myOpenAttendance();

    if (openRecord) {
      this.checkout(openRecord);
      return;
    }

    // Registrar entrada directamente con 1 toque sin abrir ventana
    this.checking.set(true);
    if (this.auth.roleName() === 'cliente' || !this.auth.hasPermission('asistencias:create')) {
      this.api.post<CheckInResponse>('asistencias/registrar-entrada/', {}).subscribe({
        next: (res) => {
          this.checking.set(false);
          const hora = this.formatTime(res.asistencia.entrada_at);
          this.toast.success(
            res.creado ? 'Llegada registrada' : 'Ya estabas dentro',
            `Registramos tu entrada a las ${hora}`,
          );
          this.load();
        },
        error: (error: unknown) => {
          this.checking.set(false);
          this.toast.error(
            'No se pudo registrar la entrada',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
    } else {
      const defaultClient = this.clients()[0]?.usuario;
      if (!defaultClient) {
        this.checking.set(false);
        this.openCreate();
        return;
      }
      this.api
        .post<Attendance>('asistencias/', {
          cliente: defaultClient,
          entrada_at: new Date().toISOString(),
          metodo_entrada: 'manual',
        })
        .subscribe({
          next: (res) => {
            this.checking.set(false);
            const hora = this.formatTime(res.entrada_at);
            this.toast.success('Entrada registrada', `Ingreso a las ${hora}`);
            this.load();
          },
          error: (error: unknown) => {
            this.checking.set(false);
            this.toast.error(
              'No se pudo registrar la entrada',
              error instanceof ApiError ? error.message : undefined,
            );
          },
        });
    }
  }

  protected async remove(record: Attendance): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar asistencia',
      message: `Se eliminará el registro de ${record.cliente_detalle.nombre} del ${formatDateTime(record.entrada_at)}.`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`asistencias/${record.id}/`).subscribe({
      next: () => {
        this.toast.success('Asistencia eliminada');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected duration(record: Attendance): string {
    if (!record.salida_at) return 'En curso';
    const minutes = Math.round(
      (new Date(record.salida_at).getTime() - new Date(record.entrada_at).getTime()) / 60000,
    );
    if (minutes < 60) return `${minutes} min`;
    return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  }

  protected methodLabel(method: string): string {
    return ATTENDANCE_METHODS[method] ?? humanize(method);
  }

  protected formatDate = formatDate;
  protected formatDateTime = formatDateTime;
  protected formatTime = formatTime;

  private averageMinutes(records: Attendance[]): string {
    const closed = records.filter((record) => record.salida_at);
    if (closed.length === 0) return '—';
    const total = closed.reduce(
      (sum, record) =>
        sum +
        (new Date(record.salida_at!).getTime() - new Date(record.entrada_at).getTime()) / 60000,
      0,
    );
    const average = Math.round(total / closed.length);
    return average < 60 ? `${average} min` : `${Math.round(average / 60)} h`;
  }
}
