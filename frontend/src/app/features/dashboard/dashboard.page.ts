import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiClient } from '../../core/api/api-client.service';
import { ApiError } from '../../core/api/api-error';
import type { Summary } from '../../core/api/api.models';
import { AuthService } from '../../core/auth/auth.service';
import { roleLabel } from '../../core/rbac/permissions';
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
  protected readonly auth = inject(AuthService);

  protected readonly summary = signal<Summary | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

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

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
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
