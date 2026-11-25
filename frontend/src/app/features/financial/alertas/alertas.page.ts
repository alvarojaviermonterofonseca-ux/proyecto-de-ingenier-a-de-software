import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { FinancialService } from '../financial.service';
import { Alerta, PaginatedResponse, FiltrosAlerta } from '../financial.models';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { PaginationComponent } from '../../../shared/pagination.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import type { PageHeaderAction } from '../../../shared/page-header.component';
import { formatDateTime } from '../../../core/utils/format';

@Component({
  selector: 'app-alertas-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    EmptyStateComponent,
    IconComponent,
    PaginationComponent,
    StatusBadgeComponent,
    PageHeaderComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-container fade-in">
      <app-page-header
        title="Centro de Alertas"
        subtitle="Notificaciones administrativas y alertas automáticas"
        [actions]="headerActions"
      />

      @if (loading()) {
        <div class="alerts-skeleton">
          @for (item of [1,2,3,4,5]; track item) {
            <div class="skeleton-alert">
              <div class="skeleton skeleton--icon"></div>
              <div class="skeleton skeleton--title"></div>
              <div class="skeleton skeleton--message"></div>
            </div>
          }
        </div>
      } @else {
        <!-- Filtros -->
        <section class="filters-card card">
          <form (ngSubmit)="aplicarFiltros()" class="filters-form">
            <div class="filters-row">
              <div class="filter-group">
                <label for="tipo">Tipo</label>
                <select
                  id="tipo"
                  class="input"
                  [(ngModel)]="filtros.tipo"
                  name="tipo"
                >
                  <option value="">Todos</option>
                  <option value="membresia_por_vencer">Membresía por vencer</option>
                  <option value="membresia_vencida">Membresía vencida</option>
                  <option value="cliente_inactivo">Cliente inactivo</option>
                  <option value="ingresos_bajos">Ingresos bajos</option>
                  <option value="gastos_altos">Gastos altos</option>
                  <option value="nuevo_gasto">Nuevo gasto</option>
                  <option value="pagos_pendientes">Pagos pendientes</option>
                  <option value="asistencia_baja">Asistencia baja</option>
                </select>
              </div>
              <div class="filter-group">
                <label for="prioridad">Prioridad</label>
                <select
                  id="prioridad"
                  class="input"
                  [(ngModel)]="filtros.prioridad"
                  name="prioridad"
                >
                  <option value="">Todas</option>
                  <option value="critica">Crítica</option>
                  <option value="alta">Alta</option>
                  <option value="media">Media</option>
                  <option value="baja">Baja</option>
                </select>
              </div>
              <div class="filter-group">
                <label for="leida">Estado</label>
                <select
                  id="leida"
                  class="input"
                  [(ngModel)]="filtros.leida"
                  name="leida"
                >
                  <option value="">Todas</option>
                  <option value="false">No leídas</option>
                  <option value="true">Leídas</option>
                </select>
              </div>
              <div class="filter-group filter-actions">
                <button type="submit" class="button button--primary">
                  <app-icon name="filter" [size]="16" />
                  Filtrar
                </button>
                <button type="button" class="button button--secondary" (click)="limpiarFiltros()">
                  <app-icon name="x" [size]="16" />
                  Limpiar
                </button>
                <button type="button" class="button button--outline" (click)="marcarTodasLeidas()">
                  <app-icon name="check-square" [size]="16" />
                  Marcar todas leídas
                </button>
              </div>
            </div>
          </form>
        </section>

        <!-- Tarjetas de resumen -->
        <section class="summary-cards">
          @for (stat of alertStats(); track stat.label) {
            <article class="stat-card" [class]="stat.color">
              <div class="stat-card__icon" [style.background]="stat.bgColor">
                <app-icon [name]="stat.icon" [size]="20" />
              </div>
              <div class="stat-card__content">
                <p class="stat-card__value">{{ stat.value }}</p>
                <p class="stat-card__label">{{ stat.label }}</p>
              </div>
            </article>
          }
        </section>

        <!-- Lista de alertas -->
        <section class="alerts-card card">
          @if (alertas().length === 0) {
            <app-empty-state
              icon="bell"
              title="Sin alertas"
              message="No hay alertas con los filtros actuales. ¡Todo tranquilo!"
            />
          } @else {
            <ul class="alerts-list">
              @for (alerta of alertas(); track alerta.id) {
                <li class="alert-item" [class]="'alert-item--' + alerta.prioridad" [class.read]="alerta.leida">
                  <div class="alert-item__icon" [style.background]="financialService.getColorPrioridadAlerta(alerta.prioridad)">
                    <app-icon [name]="getAlertaIcon(alerta.tipo)" [size]="18" />
                  </div>

                  <div class="alert-item__content">
                    <div class="alert-item__header">
                      <strong>{{ alerta.titulo }}</strong>
                      <div class="alert-item__badges">
                        <app-status-badge
                          [label]="financialService.getLabelPrioridad(alerta.prioridad)"
                          [tone]="getPrioridadTone(alerta.prioridad)"
                          size="sm"
                        />
                        <app-status-badge
                          [label]="financialService.getLabelTipoAlerta(alerta.tipo)"
                          [tone]="getTipoTone(alerta.tipo)"
                          size="sm"
                        />
                      </div>
                    </div>
                    <p class="alert-item__message">{{ alerta.mensaje }}</p>
                    <div class="alert-item__meta">
                      @if (alerta.cliente_detalle) {
                        <span>
                          <app-icon name="user" [size]="12" />
                          {{ alerta.cliente_detalle.nombre }}
                        </span>
                      }
                      <span>
                        <app-icon name="clock" [size]="12" />
                        {{ formatRelativeTime(alerta.created_at) }}
                      </span>
                      @if (alerta.leida && alerta.leida_por_detalle) {
                        <span class="read-badge">
                          <app-icon name="check-circle" [size]="12" />
                          Leída por {{ alerta.leida_por_detalle.nombre }}
                        </span>
                      }
                    </div>
                  </div>

                  <div class="alert-item__actions">
                    @if (!alerta.leida) {
                      <button
                        class="icon-button"
                        (click)="marcarLeida(alerta.id)"
                        aria-label="Marcar como leída"
                      >
                        <app-icon name="check" [size]="18" />
                      </button>
                    }
                  </div>
                </li>
              }
            </ul>

            @if (pagination().totalPages > 1) {
              <div class="pagination-container">
                <app-pagination
                  [page]="pagination().currentPage"
                  [count]="pagination().totalItems"
                  (pageChange)="cambiarPagina($event)"
                />
              </div>
            }
          }
        </section>
      }
    </div>
  `,
  styles: [`
    .page-container {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .alerts-skeleton {
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .skeleton-alert {
      display: flex;
      gap: 1rem;
      padding: 1rem;
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
    }

    .skeleton--icon {
      width: 3rem;
      height: 3rem;
      border-radius: 0.75rem;
    }

    .skeleton--title {
      flex: 1;
      height: 1rem;
      border-radius: 0.25rem;
      margin-bottom: 0.5rem;
    }

    .skeleton--message {
      flex: 1;
      height: 0.75rem;
      border-radius: 0.25rem;
    }

    .filters-card {
      padding: 1.5rem;
    }

    .filters-form {
      margin: 0;
    }

    .filters-row {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: 1rem;
    }

    .filter-group {
      display: flex;
      flex-direction: column;
      gap: 0.375rem;
      min-width: 160px;
      flex: 1;
    }

    .filter-group.filter-actions {
      flex-direction: row;
      align-items: center;
      min-width: auto;
      flex: none;
    }

    .filter-group label {
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--color-text-muted);
      text-transform: uppercase;
      letter-spacing: 0.025em;
    }

    .filter-group .input {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: 0.375rem;
      background: var(--color-bg);
      color: var(--color-text);
      font-size: 0.875rem;
      transition: all 0.15s ease;
    }

    .filter-group .input:focus {
      outline: none;
      border-color: var(--color-primary);
      box-shadow: 0 0 0 3px var(--color-primary-focus);
    }

    .summary-cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }

    .stat-card {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 1.25rem;
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
    }

    .stat-card--primary { border-left: 4px solid var(--color-primary); }
    .stat-card--warning { border-left: 4px solid var(--color-warning); }
    .stat-card--danger { border-left: 4px solid var(--color-danger); }
    .stat-card--info { border-left: 4px solid var(--color-info); }

    .stat-card__icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 3rem;
      height: 3rem;
      border-radius: 0.75rem;
      color: white;
    }

    .stat-card__content {
      flex: 1;
    }

    .stat-card__value {
      margin: 0;
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--color-text);
      line-height: 1.2;
    }

    .stat-card__label {
      margin: 0;
      font-size: 0.875rem;
      color: var(--color-text-muted);
    }

    .alerts-card {
      padding: 0;
    }

    .alerts-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .alert-item {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--color-border);
      transition: background 0.15s ease;
    }

    .alert-item:last-child {
      border-bottom: none;
    }

    .alert-item:hover {
      background: var(--color-bg);
    }

    .alert-item.read {
      opacity: 0.7;
      background: var(--color-bg);
    }

    .alert-item--critica { border-left: 4px solid var(--color-danger); }
    .alert-item--alta { border-left: 4px solid var(--color-warning); }
    .alert-item--media { border-left: 4px solid var(--color-info); }
    .alert-item--baja { border-left: 4px solid var(--color-text-muted); }

    .alert-item__icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 3rem;
      height: 3rem;
      border-radius: 0.75rem;
      color: white;
      flex-shrink: 0;
    }

    .alert-item__content {
      flex: 1;
      min-width: 0;
    }

    .alert-item__header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 0.5rem;
    }

    .alert-item__header strong {
      font-size: 1rem;
      color: var(--color-text);
    }

    .alert-item.read .alert-item__header strong {
      color: var(--color-text-muted);
    }

    .alert-item__badges {
      display: flex;
      gap: 0.375rem;
      flex-wrap: wrap;
    }

    .alert-item__message {
      margin: 0 0 0.5rem;
      color: var(--color-text-muted);
      line-height: 1.5;
    }

    .alert-item__meta {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      font-size: 0.75rem;
      color: var(--color-text-muted);
    }

    .alert-item__meta span {
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }

    .read-badge {
      color: var(--color-success) !important;
    }

    .alert-item__actions {
      flex-shrink: 0;
    }

    .icon-button {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 2.5rem;
      height: 2.5rem;
      border: none;
      background: var(--color-bg);
      border-radius: 0.5rem;
      color: var(--color-text-muted);
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .icon-button:hover {
      background: var(--color-primary);
      color: white;
    }

    .pagination-container {
      padding: 1rem 1.5rem;
      border-top: 1px solid var(--color-border);
    }

    @media (max-width: 768px) {
      .filters-row {
        flex-direction: column;
        align-items: stretch;
      }

      .filter-group {
        min-width: 0;
      }

      .filter-group.filter-actions {
        flex-direction: column;
      }

      .alert-item__header {
        flex-direction: column;
        align-items: flex-start;
      }
    }
  `],
})
export class AlertasPage implements OnInit {
  protected readonly financialService = inject(FinancialService);
  protected readonly toast = inject(ToastService);

  protected readonly alertas = signal<Alerta[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadingStats = signal(false);

  protected filtros: FiltrosAlerta = {
    tipo: '',
    prioridad: '',
    leida: undefined,
  };

  protected readonly pagination = signal({
    currentPage: 1,
    totalPages: 1,
    totalItems: 0,
    pageSize: 25,
  });

  protected readonly headerActions: PageHeaderAction[] = [
    {
      label: 'Marcar todas leídas',
      icon: 'check-square',
      action: () => this.marcarTodasLeidas(),
      class: 'button--outline',
    },
  ];

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = {
      page: this.pagination().currentPage,
      page_size: this.pagination().pageSize,
    };

    const f = this.filtros;
    if (f['tipo']) params['tipo'] = f['tipo'];
    if (f['prioridad']) params['prioridad'] = f['prioridad'];
    if (f['leida'] !== undefined) params['leida'] = f['leida'] ? 1 : 0;

    this.financialService.getAlertas(params).subscribe({
      next: (response: PaginatedResponse<Alerta>) => {
        this.alertas.set(response.results);
        this.pagination.update(p => ({
          ...p,
          currentPage: response.results.length > 0 ? p.currentPage : 1,
          totalPages: Math.ceil(response.count / p.pageSize),
          totalItems: response.count,
        }));
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.error('Error al cargar alertas', err.message);
      },
    });
  }

  protected aplicarFiltros(): void {
    this.pagination.update(p => ({ ...p, currentPage: 1 }));
    this.load();
  }

  protected limpiarFiltros(): void {
    this.filtros.tipo = '';
    this.filtros.prioridad = '';
    this.filtros.leida = undefined;
    this.aplicarFiltros();
  }

  protected cambiarPagina(page: number): void {
    this.pagination.update(p => ({ ...p, currentPage: page }));
    this.load();
  }

  protected marcarLeida(id: number): void {
    this.financialService.marcarAlertaLeida(id).subscribe({
      next: () => {
        this.alertas.update(alertas =>
          alertas.map(a => a.id === id ? { ...a, leida: true, leida_at: new Date().toISOString() } : a)
        );
        this.toast.success('Alerta marcada como leída');
      },
      error: (err) => {
        this.toast.error('Error', err.message);
      },
    });
  }

  protected marcarTodasLeidas(): void {
    this.financialService.marcarTodasAlertasLeidas().subscribe({
      next: (result) => {
        this.alertas.update(alertas =>
          alertas.map(a => ({ ...a, leida: true, leida_at: new Date().toISOString() }))
        );
        this.toast.success(result.mensaje, `${result.cantidad} alertas marcadas`);
      },
      error: (err) => {
        this.toast.error('Error', err.message);
      },
    });
  }

  protected readonly alertStats = computed(() => {
    const a = this.alertas();
    const noLeidas = a.filter(x => !x.leida).length;
    const criticas = a.filter(x => x.prioridad === 'critica').length;
    const altas = a.filter(x => x.prioridad === 'alta').length;

    return [
      { label: 'Total Alertas', value: a.length, icon: 'bell', color: 'stat-card--primary', bgColor: '#6366f1' },
      { label: 'No Leídas', value: noLeidas, icon: 'alert-circle', color: 'stat-card--warning', bgColor: '#f59e0b' },
      { label: 'Críticas', value: criticas, icon: 'alert-triangle', color: 'stat-card--danger', bgColor: '#ef4444' },
      { label: 'Altas', value: altas, icon: 'trending-up', color: 'stat-card--info', bgColor: '#3b82f6' },
    ];
  });

  protected getAlertaIcon(tipo: string): string {
    const iconos: Record<string, string> = {
      membresia_por_vencer: 'clock',
      membresia_vencida: 'alert-circle',
      cliente_inactivo: 'user-x',
      ingresos_bajos: 'trending-down',
      gastos_altos: 'trending-up',
      nuevo_gasto: 'credit-card',
      pagos_pendientes: 'dollar-sign',
      asistencia_baja: 'activity',
    };
    return iconos[tipo] || 'alert-triangle';
  }

  protected getPrioridadTone(prioridad: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    switch (prioridad) {
      case 'critica': return 'danger';
      case 'alta': return 'warning';
      case 'media': return 'info';
      case 'baja': return 'neutral';
      default: return 'neutral';
    }
  }

  protected getTipoTone(tipo: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    const tonos: Record<string, 'success' | 'danger' | 'warning' | 'info' | 'neutral'> = {
      membresia_por_vencer: 'warning',
      membresia_vencida: 'danger',
      cliente_inactivo: 'info',
      ingresos_bajos: 'danger',
      gastos_altos: 'warning',
      nuevo_gasto: 'info',
      pagos_pendientes: 'warning',
      asistencia_baja: 'info',
    };
    return tonos[tipo] || 'neutral';
  }

  protected formatRelativeTime(fecha: string): string {
    const diff = Date.now() - new Date(fecha).getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Ahora';
    if (minutes < 60) return `Hace ${minutes} min`;
    if (hours < 24) return `Hace ${hours} h`;
    if (days < 7) return `Hace ${days} d`;
    return new Date(fecha).toLocaleDateString('es-CO');
  }

  protected readonly formatDateTime = formatDateTime;
}