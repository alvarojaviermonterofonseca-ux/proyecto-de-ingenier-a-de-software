import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { ClientProfile, Notification, UserSummary } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { ConfirmService } from '../../core/ui/confirm.service';
import { ToastService } from '../../core/ui/toast.service';
import {
  NOTIFICATION_STATES,
  NOTIFICATION_TYPES,
  dateTimeInput,
  formatDateTime,
} from '../../core/utils/format';
import { AvatarComponent } from '../../shared/avatar.component';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { ModalComponent } from '../../shared/modal.component';
import { PageHeaderComponent } from '../../shared/page-header.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

interface RecipientOption {
  id: number;
  nombre: string;
  detail: string;
}

@Component({
  selector: 'app-notifications-page',
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
  templateUrl: './notifications.page.html',
  styleUrl: './notifications.page.css',
})
export class NotificationsPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly notifications = signal<Notification[]>([]);
  protected readonly users = signal<UserSummary[]>([]);
  protected readonly clients = signal<ClientProfile[]>([]);
  protected readonly search = signal('');
  protected readonly stateFilter = signal('');
  protected readonly typeFilter = signal('');
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly modalOpen = signal(false);
  protected readonly editing = signal<Notification | null>(null);
  protected readonly notificationTypes = NOTIFICATION_TYPES;
  protected readonly notificationStates = NOTIFICATION_STATES;

  protected readonly canTargetClients = computed(() => {
    const role = this.auth.roleName();
    return role === 'entrenador' || role === 'terapeuta';
  });

  protected readonly recipients = computed<RecipientOption[]>(() => {
    if (this.auth.isAdmin()) {
      return this.users().map((user) => ({
        id: user.id,
        nombre: user.nombre,
        detail: user.rol_nombre,
      }));
    }
    const options: RecipientOption[] = [];
    const current = this.auth.user();
    if (current) {
      options.push({ id: current.id, nombre: current.nombre, detail: 'Mi cuenta' });
    }
    if (this.canTargetClients()) {
      for (const client of this.clients()) {
        if (client.usuario === current?.id) continue;
        options.push({
          id: client.usuario,
          nombre: client.usuario_detalle.nombre,
          detail: 'Cliente asignado',
        });
      }
    }
    return options;
  });

  protected readonly filtered = computed(() => {
    const query = this.search().trim().toLowerCase();
    const state = this.stateFilter();
    const type = this.typeFilter();
    return this.notifications().filter((notification) => {
      if (state && notification.estado !== state) return false;
      if (type && notification.tipo !== type) return false;
      if (!query) return true;
      return (
        notification.titulo.toLowerCase().includes(query) ||
        notification.mensaje.toLowerCase().includes(query) ||
        notification.usuario_detalle.nombre.toLowerCase().includes(query)
      );
    });
  });

  protected readonly form = this.formBuilder.nonNullable.group({
    usuario: [0, [Validators.required]],
    tipo: ['sistema', [Validators.required]],
    titulo: ['', [Validators.required]],
    mensaje: ['', [Validators.required]],
    programada_at: [''],
    estado: ['pendiente', [Validators.required]],
  });

  ngOnInit(): void {
    this.load();
    if (this.auth.isAdmin()) {
      this.api.getAll<UserSummary>('usuarios/').subscribe({
        next: (users) => this.users.set(users),
        error: () => this.users.set([]),
      });
    }
    if (this.canTargetClients()) {
      this.api.getAll<ClientProfile>('clientes/').subscribe({
        next: (clients) => this.clients.set(clients),
        error: () => this.clients.set([]),
      });
    }
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Notification>('notificaciones/').subscribe({
      next: (notifications) => {
        this.notifications.set(
          notifications.sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
          ),
        );
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof ApiError ? error.message : 'No se pudieron cargar las notificaciones.');
      },
    });
  }

  protected openCreate(): void {
    const current = this.auth.user();
    this.editing.set(null);
    this.formError.set(null);
    this.form.reset({
      usuario: current?.id ?? 0,
      tipo: 'sistema',
      titulo: '',
      mensaje: '',
      programada_at: '',
      estado: 'pendiente',
    });
    this.configureRecipientControl();
    this.modalOpen.set(true);
  }

  protected openEdit(notification: Notification): void {
    this.editing.set(notification);
    this.formError.set(null);
    this.form.reset({
      usuario: notification.usuario,
      tipo: notification.tipo,
      titulo: notification.titulo,
      mensaje: notification.mensaje,
      programada_at: dateTimeInput(notification.programada_at),
      estado: notification.estado,
    });
    this.configureRecipientControl();
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (!this.saving()) {
      this.form.controls.usuario.enable();
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
    const payload = {
      usuario: raw.usuario,
      tipo: raw.tipo,
      titulo: raw.titulo.trim(),
      mensaje: raw.mensaje.trim(),
      programada_at: raw.programada_at ? new Date(raw.programada_at).toISOString() : null,
      estado: raw.estado,
    };
    this.saving.set(true);
    const request = editing
      ? this.api.patch<Notification>(`notificaciones/${editing.id}/`, payload)
      : this.api.post<Notification>('notificaciones/', payload);
    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.form.controls.usuario.enable();
        this.modalOpen.set(false);
        this.toast.success(editing ? 'Notificación actualizada' : 'Notificación enviada');
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.formError.set(
          error instanceof ApiError ? error.message : 'No se pudo guardar la notificación.',
        );
      },
    });
  }

  protected async remove(notification: Notification): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar notificación',
      message: `Se eliminará "${notification.titulo}".`,
      confirmLabel: 'Eliminar',
    });
    if (!accepted) return;
    this.api.delete(`notificaciones/${notification.id}/`).subscribe({
      next: () => {
        this.toast.success('Notificación eliminada');
        this.load();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo eliminar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected updateFilter(
    target: 'state' | 'type',
    value: string,
  ): void {
    if (target === 'state') this.stateFilter.set(value);
    else this.typeFilter.set(value);
  }

  protected stateTone(state: string): 'success' | 'warning' | 'danger' | 'neutral' {
    if (state === 'enviada') return 'success';
    if (state === 'pendiente') return 'warning';
    if (state === 'fallida') return 'danger';
    return 'neutral';
  }

  protected typeLabel(type: string): string {
    return NOTIFICATION_TYPES[type] ?? type;
  }

  protected stateLabel(state: string): string {
    return NOTIFICATION_STATES[state] ?? state;
  }

  protected formatDateTime = formatDateTime;

  private configureRecipientControl(): void {
    if (this.auth.isAdmin()) {
      this.form.controls.usuario.enable();
    } else {
      this.form.controls.usuario.disable();
    }
  }
}
