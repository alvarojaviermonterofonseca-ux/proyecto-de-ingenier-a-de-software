import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Summary } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { roleLabel } from '../../core/rbac/permissions';
import { ToastService } from '../../core/ui/toast.service';
import { formatDateTime, humanize, relativeDate } from '../../core/utils/format';
import { EmptyStateComponent } from '../../shared/empty-state.component';
import { IconComponent } from '../../shared/icon.component';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

interface MetricCard {
  label: string;
  value: number;
  hint: string;
  icon: string;
  accent?: boolean;
}

interface QuickAction {
  label: string;
  route: string;
  icon: string;
  permission: string | string[];
  queryParams?: Record<string, string | number>;
  adminOnly?: boolean;
}

interface CheckInResponse {
  creado?: boolean;
  mensaje: string;
  asistencia: { id: number; entrada_at: string; salida_at?: string | null };
}

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [
    RouterLink,
    IconComponent,
    EmptyStateComponent,
    StatusBadgeComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.page.html',
  styleUrl: './dashboard.page.css',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly toast = inject(ToastService);
  protected readonly auth = inject(AuthService);

  protected readonly summary = signal<Summary | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly checkingIn = signal(false);
  protected readonly checkingOut = signal(false);

  protected readonly visitasSemana = computed(
    () => this.summary()?.metricas.visitas_semana ?? 0,
  );
  protected readonly diasSemana = computed(
    () => this.summary()?.metricas.visitas_semana_dias ?? [],
  );
  protected readonly asistenciaAbierta = computed(
    () => this.summary()?.asistencia_abierta ?? null,
  );
  protected readonly semanaLabel = computed(() => {
    const dias = this.diasSemana();
    if (dias.length === 0) return '';
    return `Semana del ${this.diaCorto(dias[0].fecha)} al ${this.diaCorto(dias[dias.length - 1].fecha)}`;
  });

  protected readonly greeting = computed(() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Buenos días';
    if (hour < 18) return 'Buenas tardes';
    return 'Buenas noches';
  });

  protected readonly role = computed(() => roleLabel(this.auth.roleName()));

  protected readonly metrics = computed<MetricCard[]>(() => {
    const values = this.summary()?.metricas;
    if (!values) {
      return [];
    }
    const cards: MetricCard[] = [
      {
        label: 'Clientes activos',
        value: values.clientes_activos,
        hint: 'En seguimiento',
        icon: 'users',
      },
      {
        label: 'Asistencias hoy',
        value: values.asistencias_hoy,
        hint: `${values.asistencias_abiertas} sin registrar salida`,
        icon: 'clock',
      },
      {
        label: 'Entrenamientos hoy',
        value: values.entrenamientos_hoy,
        hint: 'Sesiones agendadas',
        icon: 'calendar',
      },
      {
        label: 'Registros por revisar',
        value: values.registros_comida_pendientes,
        hint: 'Evidencias de comida',
        icon: 'camera',
        accent: values.registros_comida_pendientes > 0,
      },
      {
        label: 'Planes de entrenamiento',
        value: values.planes_entrenamiento_activos,
        hint: 'Activos',
        icon: 'clipboard',
      },
      {
        label: 'Notificaciones',
        value: values.notificaciones_pendientes,
        hint: 'Pendientes de envío',
        icon: 'bell',
      },
    ];
    return cards.filter((card) => this.isVisible(card.label));
  });

  protected readonly actions = computed<QuickAction[]>(() => {
    const actions: QuickAction[] = [
      {
        label: 'Nuevo cliente',
        route: '/clientes',
        icon: 'user-plus',
        permission: ['clientes:create', 'usuarios:create'],
        queryParams: { nuevo: 1 },
        adminOnly: true,
      },
      {
        label: 'Registrar asistencia',
        route: '/asistencias',
        icon: 'clock',
        permission: 'asistencias:create',
        queryParams: { nuevo: 1 },
      },
      {
        label: 'Nuevo entrenamiento',
        route: '/entrenamientos',
        icon: 'calendar',
        permission: 'entrenamientos:create',
        queryParams: { nuevo: 1 },
      },
      {
        label: 'Revisar comidas',
        route: '/registros-comida',
        icon: 'camera',
        permission: 'registros-comida:edit',
      },
    ];
    return actions.filter((action) => this.isAllowed(action));
  });

  ngOnInit(): void {
    this.load();
  }

  protected load(silent = false): void {
    if (!silent) {
      this.loading.set(true);
      this.error.set(null);
    }
    this.api.get<Summary>('resumen/').subscribe({
      next: (summary) => {
        this.summary.set(summary);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof ApiError ? error.message : 'No se pudo cargar el resumen.',
        );
      },
    });
  }

  protected registrarLlegada(): void {
    if (this.checkingIn() || this.asistenciaAbierta()) return;
    this.checkingIn.set(true);
    this.api.post<CheckInResponse>('asistencias/registrar-entrada/', {}).subscribe({
      next: (respuesta) => {
        this.checkingIn.set(false);
        const hora = this.horaDe(respuesta.asistencia.entrada_at);
        this.toast.success(
          respuesta.creado ? 'Llegada registrada' : 'Ya estabas dentro',
          respuesta.creado
            ? `Registramos tu entrada a las ${hora}`
            : `Tu entrada sigue abierta desde las ${hora}`,
        );
        this.load(true);
      },
      error: (error: unknown) => {
        this.checkingIn.set(false);
        this.toast.error(
          'No se pudo registrar tu llegada',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected registrarSalida(): void {
    if (this.checkingOut() || !this.asistenciaAbierta()) return;
    this.checkingOut.set(true);
    this.api.post<CheckInResponse>('asistencias/registrar-salida/', {}).subscribe({
      next: (respuesta) => {
        this.checkingOut.set(false);
        const hora = respuesta.asistencia.salida_at
          ? this.horaDe(respuesta.asistencia.salida_at)
          : '';
        this.toast.success('Salida registrada', `Cerramos tu visita a las ${hora}`);
        this.load(true);
      },
      error: (error: unknown) => {
        this.checkingOut.set(false);
        this.toast.error(
          'No se pudo registrar tu salida',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected horaDe(valor: string): string {
    return new Intl.DateTimeFormat('es-CO', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(valor));
  }

  private diaCorto(iso: string): string {
    return new Intl.DateTimeFormat('es-CO', {
      day: 'numeric',
      month: 'short',
    }).format(new Date(`${iso}T12:00:00`));
  }

  protected notificationTone(estado: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    if (estado === 'enviada') return 'success';
    if (estado === 'fallida') return 'danger';
    if (estado === 'pendiente') return 'warning';
    return 'neutral';
  }

  protected notificationLabel(estado: string): string {
    const labels: Record<string, string> = {
      pendiente: 'Pendiente',
      enviada: 'Enviada',
      fallida: 'Fallida',
      cancelada: 'Cancelada',
    };
    return labels[estado] ?? estado;
  }

  protected attendanceTone(salida: string | null): 'success' | 'warning' {
    return salida ? 'success' : 'warning';
  }

  protected readonly formatDateTime = formatDateTime;
  protected readonly relativeDate = relativeDate;
  protected readonly humanize = humanize;

  private isAllowed(action: QuickAction): boolean {
    if (action.adminOnly && !this.auth.isAdmin()) {
      return false;
    }
    const codes = Array.isArray(action.permission) ? action.permission : [action.permission];
    return codes.every((code) => this.auth.hasPermission(code));
  }

  private isVisible(label: string): boolean {
    const map: Record<string, string> = {
      'Clientes activos': 'clientes:view',
      'Asistencias hoy': 'asistencias:view',
      'Entrenamientos hoy': 'entrenamientos:view',
      'Registros por revisar': 'registros-comida:view',
      'Planes de entrenamiento': 'planes-entrenamiento:view',
      Notificaciones: 'notificaciones:view',
    };
    return this.auth.hasPermission(map[label]);
  }
}
