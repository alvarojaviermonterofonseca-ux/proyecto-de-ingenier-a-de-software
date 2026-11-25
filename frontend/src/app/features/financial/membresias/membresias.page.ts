import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { FinancialService } from '../financial.service';
import { Membresia, PaginatedResponse, FiltrosMembresia } from '../financial.models';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { PaginationComponent } from '../../../shared/pagination.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import type { PageHeaderAction } from '../../../shared/page-header.component';
import { formatDate, todayInput } from '../../../core/utils/format';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ApiError } from '../../../core/api/api-error';
import { MembresiaFormComponent } from '../forms/membresia-form.component';
import { AccionMembresia, MembresiaAccionComponent } from '../forms/membresia-accion.component';

@Component({
  selector: 'app-membresias-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    EmptyStateComponent,
    IconComponent,
    PaginationComponent,
    StatusBadgeComponent,
    PageHeaderComponent,
    MembresiaFormComponent,
    MembresiaAccionComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-container fade-in">
      <app-page-header
        title="Membresías"
        subtitle="Gestión de membresías y planes de clientes"
        [actions]="headerActions"
      />

      @if (loading()) {
        <div class="table-skeleton">
          @for (item of [1,2,3,4,5]; track item) {
            <div class="skeleton-row">
              <div class="skeleton skeleton--cell"></div>
              <div class="skeleton skeleton--cell"></div>
              <div class="skeleton skeleton--cell"></div>
              <div class="skeleton skeleton--cell"></div>
              <div class="skeleton skeleton--cell"></div>
              <div class="skeleton skeleton--cell"></div>
              <div class="skeleton skeleton--cell"></div>
            </div>
          }
        </div>
      } @else {
        <!-- Filtros -->
        <section class="filters-card card">
          <form (ngSubmit)="aplicarFiltros()" class="filters-form">
            <div class="filters-row">
              <div class="filter-group">
                <label for="estado">Estado</label>
                <select
                  id="estado"
                  class="input"
                  [(ngModel)]="filtros.estado"
                  name="estado"
                >
                  <option value="">Todos</option>
                  <option value="activa">Activa</option>
                  <option value="por_vencer">Por vencer</option>
                  <option value="vencida">Vencida</option>
                  <option value="cancelada">Cancelada</option>
                  <option value="congelada">Congelada</option>
                </select>
              </div>
              <div class="filter-group">
                <label for="tipo">Tipo</label>
                <select
                  id="tipo"
                  class="input"
                  [(ngModel)]="filtros.tipo"
                  name="tipo"
                >
                  <option value="">Todos</option>
                  <option value="mensual">Mensual</option>
                  <option value="trimestral">Trimestral</option>
                  <option value="semestral">Semestral</option>
                  <option value="anual">Anual</option>
                  <option value="visita">Visita única</option>
                  <option value="personalizada">Personalizada</option>
                </select>
              </div>
              <div class="filter-group">
                <label for="entrenador">Entrenador</label>
                <select
                  id="entrenador"
                  class="input"
                  [(ngModel)]="filtros.entrenador_asignado"
                  name="entrenador_asignado"
                >
                  <option value="">Todos</option>
                  @for (ent of entrenadores(); track ent.id) {
                    <option [value]="ent.id">{{ ent.nombre }}</option>
                  }
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
                <button type="button" class="button button--outline" (click)="exportar()">
                  <app-icon name="download" [size]="16" />
                  Exportar
                </button>
              </div>
            </div>
          </form>
        </section>

        <!-- Tarjetas de resumen -->
        <section class="summary-cards">
          @for (stat of membershipStats(); track stat.label) {
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

        <!-- Tabla de membresías -->
        <section class="table-card card">
          <div class="table-responsive">
            @if (membresias().length === 0) {
              <app-empty-state
                icon="id-card"
                title="Sin membresías"
                message="No se encontraron membresías con los filtros actuales."
              />
            } @else {
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Cliente</th>
                    <th>Tipo</th>
                    <th>Vigencia</th>
                    <th>Estado</th>
                    <th>Días p/ vencer</th>
                    <th>Precio</th>
                    <th>Entrenador</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  @for (m of membresias(); track m.id) {
                    <tr>
                      <td>
                        <div class="cell-client">
                          <strong>{{ m.cliente_detalle.nombre }}</strong>
                          <small>{{ m.cliente_detalle.correo }}</small>
                        </div>
                      </td>
                      <td>
                        <span class="type-badge">{{ formatTipoMembresia(m.tipo) }}</span>
                      </td>
                      <td>
                        <div class="cell-dates">
                          <span>{{ formatDate(m.fecha_inicio) }} - {{ formatDate(m.fecha_fin) }}</span>
                          @if (m.fecha_ultima_renovacion) {
                            <small>Renovada: {{ formatDate(m.fecha_ultima_renovacion) }}</small>
                          }
                        </div>
                      </td>
                      <td>
                        <app-status-badge
                          [label]="formatEstadoMembresia(m.estado)"
                          [tone]="getEstadoTone(m.estado)"
                        />
                      </td>
                      <td [class.warning]="m.dias_para_vencer <= 7 && m.dias_para_vencer > 0" [class.danger]="m.dias_para_vencer < 0">
                        @if (m.dias_para_vencer < 0) {
                          <span class="text-danger">Vencida hace {{ Math.abs(m.dias_para_vencer) }} días</span>
                        } @else {
                          {{ m.dias_para_vencer }} días
                        }
                      </td>
                      <td class="cell-value">{{ financialService.formatearMoneda(m.precio) }}</td>
                      <td>
                        @if (m.entrenador_detalle) {
                          <small>{{ m.entrenador_detalle.nombre }}</small>
                        } @else {
                          <span class="text-muted">—</span>
                        }
                      </td>
                      <td>
                        <div class="row-actions">
                          @if (m.estado !== 'cancelada') {
                            <button type="button" class="button button--secondary button--sm" (click)="renovar(m)">
                              Renovar
                            </button>
                          }
                          @if (m.estado === 'activa' || m.estado === 'por_vencer') {
                            <button type="button" class="button button--secondary button--sm" (click)="congelar(m)">
                              Congelar
                            </button>
                          }
                          @if (m.estado === 'congelada') {
                            <button type="button" class="button button--secondary button--sm" (click)="activar(m)">
                              Reactivar
                            </button>
                          }
                        </div>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </div>

          @if (pagination().totalPages > 1) {
            <div class="pagination-container">
              <app-pagination
                [page]="pagination().currentPage"
                [count]="pagination().totalItems"
                (pageChange)="cambiarPagina($event)"
              />
            </div>
          }
        </section>
      }

      <app-membresia-form
        [open]="formularioAbierto()"
        (closed)="formularioAbierto.set(false)"
        (saved)="alGuardarMembresia()"
      />
      <app-membresia-accion
        [accion]="accion()"
        (closed)="accion.set(null)"
        (saved)="alGuardarMembresia()"
      />
    </div>
  `,
  styles: [`
    .page-container {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .table-skeleton {
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
      padding: 1rem;
    }

    .skeleton-row {
      display: grid;
      grid-template-columns: 200px 120px 180px 140px 140px 140px 160px;
      gap: 1rem;
      padding: 0.75rem 0;
      border-bottom: 1px solid var(--color-border);
    }

    .skeleton-row:last-child {
      border-bottom: none;
    }

    .skeleton--cell {
      height: 1rem;
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
    .stat-card--success { border-left: 4px solid var(--color-success); }
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

    .table-card {
      padding: 0;
      overflow: hidden;
    }

    .table-responsive {
      overflow-x: auto;
    }

    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }

    .data-table thead {
      background: var(--color-bg);
    }

    .data-table th {
      padding: 0.875rem 1rem;
      text-align: left;
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--color-text-muted);
      border-bottom: 1px solid var(--color-border);
      white-space: nowrap;
    }

    .data-table td {
      padding: 0.875rem 1rem;
      border-bottom: 1px solid var(--color-border);
      vertical-align: middle;
    }

    .data-table tbody tr:last-child td {
      border-bottom: none;
    }

    .data-table tbody tr:hover td {
      background: var(--color-bg);
    }

    .cell-client {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }

    .cell-client strong {
      color: var(--color-text);
    }

    .cell-client small {
      color: var(--color-text-muted);
      font-size: 0.75rem;
    }

    .type-badge {
      display: inline-block;
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-weight: 500;
      background: var(--color-primary-light);
      color: var(--color-primary);
    }

    .cell-dates {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }

    .cell-dates span {
      white-space: nowrap;
    }

    .cell-dates small {
      color: var(--color-text-muted);
    }

    .cell-value {
      font-variant-numeric: tabular-nums;
    }

    .text-warning { color: var(--color-warning); font-weight: 600; }
    .text-danger { color: var(--color-danger); font-weight: 600; }
    .text-muted { color: var(--color-text-muted); }

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

      .data-table th,
      .data-table td {
        padding: 0.625rem 0.75rem;
      }
    }
  `],
})
export class MembresiasPage implements OnInit {
  protected readonly financialService = inject(FinancialService);
  protected readonly toast = inject(ToastService);

  protected readonly membresias = signal<Membresia[]>([]);
  protected readonly entrenadores = signal<{ id: number; nombre: string }[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadingStats = signal(false);

  protected filtros: FiltrosMembresia = {
    estado: '',
    tipo: '',
    entrenador_asignado: undefined,
  };

  protected readonly pagination = signal({
    currentPage: 1,
    totalPages: 1,
    totalItems: 0,
    pageSize: 25,
  });

  protected readonly headerActions: PageHeaderAction[] = [
    {
      label: 'Nueva Membresía',
      icon: 'plus',
      action: () => this.nuevaMembresia(),
      class: 'button--primary',
    },
    {
      label: 'Exportar',
      icon: 'download',
      action: () => this.exportar(),
      class: 'button--outline',
    },
  ];

  ngOnInit(): void {
    this.loadEntrenadores();
    this.load();
    this.loadEstadisticas();
  }

  protected load(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = {
      page: this.pagination().currentPage,
      page_size: this.pagination().pageSize,
    };

    const f = this.filtros;
    if (f['estado']) params['estado'] = f['estado'];
    if (f['tipo']) params['tipo'] = f['tipo'];
    if (f['entrenador_asignado']) params['entrenador_asignado'] = f['entrenador_asignado'];

    this.financialService.getMembresias(params).subscribe({
      next: (response: PaginatedResponse<Membresia>) => {
        this.membresias.set(response.results);
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
        this.toast.error('Error al cargar membresías', err.message);
      },
    });
  }

  protected loadEntrenadores(): void {
    // Cargar entrenadores desde el endpoint de usuarios con rol entrenador
    // Por simplicidad, usamos un placeholder
    this.entrenadores.set([]);
  }

  protected aplicarFiltros(): void {
    this.pagination.update(p => ({ ...p, currentPage: 1 }));
    this.load();
  }

  protected limpiarFiltros(): void {
    this.filtros.estado = '';
    this.filtros.tipo = '';
    this.filtros.entrenador_asignado = undefined;
    this.aplicarFiltros();
  }

  protected cambiarPagina(page: number): void {
    this.pagination.update(p => ({ ...p, currentPage: page }));
    this.load();
  }

  protected exportar(): void {
    const params: Record<string, string | number> = {};
    const f = this.filtros;
    if (f['estado']) params['estado'] = f['estado'];
    if (f['tipo']) params['tipo'] = f['tipo'];
    if (f['entrenador_asignado']) params['entrenador_asignado'] = f['entrenador_asignado'];

    this.financialService.exportMembresias(params).subscribe({
      next: (blob) => {
        this.financialService.guardarArchivo(blob, `membresias_${todayInput()}.csv`);
        this.toast.success('Exportación completada', 'El archivo CSV se ha descargado');
      },
      error: (err) => {
        this.toast.error('Error al exportar', err.message);
      },
    });
  }

  private readonly confirm = inject(ConfirmService);
  protected readonly formularioAbierto = signal(false);
  protected readonly accion = signal<AccionMembresia | null>(null);
  /** Conteo por estado de todas las membresías, no solo de la página visible. */
  protected readonly conteoPorEstado = signal<Record<string, number>>({});

  protected nuevaMembresia(): void {
    this.formularioAbierto.set(true);
  }

  protected alGuardarMembresia(): void {
    this.formularioAbierto.set(false);
    this.accion.set(null);
    this.load();
    this.loadEstadisticas();
  }

  protected renovar(membresia: Membresia): void {
    this.accion.set({ tipo: 'renovar', membresia });
  }

  protected congelar(membresia: Membresia): void {
    this.accion.set({ tipo: 'congelar', membresia });
  }

  protected async activar(membresia: Membresia): Promise<void> {
    const aceptado = await this.confirm.confirm({
      title: 'Reactivar membresía',
      message: `La membresía de ${membresia.cliente_detalle.nombre} volverá a estar vigente.`,
      confirmLabel: 'Reactivar',
    });
    if (!aceptado) return;
    this.financialService.activarMembresia(membresia.id).subscribe({
      next: () => {
        this.toast.success('Membresía reactivada');
        this.alGuardarMembresia();
      },
      error: (error: unknown) => {
        this.toast.error('No se pudo reactivar', error instanceof ApiError ? error.message : undefined);
      },
    });
  }

  protected loadEstadisticas(): void {
    this.financialService.getEstadisticasMembresias().subscribe({
      next: (stats) => this.conteoPorEstado.set(stats.por_estado),
    });
  }

  protected readonly membershipStats = computed(() => {
    const conteo = this.conteoPorEstado();
    const porVencer = conteo['por_vencer'] ?? 0;
    const activas = (conteo['activa'] ?? 0) + porVencer;
    const vencidas = conteo['vencida'] ?? 0;
    const congeladas = conteo['congelada'] ?? 0;

    return [
      { label: 'Activas', value: activas, icon: 'user-check', color: 'stat-card--success', bgColor: '#22c55e' },
      { label: 'Por Vencer', value: porVencer, icon: 'clock', color: 'stat-card--warning', bgColor: '#f59e0b' },
      { label: 'Vencidas', value: vencidas, icon: 'alert-circle', color: 'stat-card--danger', bgColor: '#ef4444' },
      { label: 'Congeladas', value: congeladas, icon: 'pause-circle', color: 'stat-card--info', bgColor: '#3b82f6' },
    ];
  });

  protected formatTipoMembresia(tipo: string): string {
    const labels: Record<string, string> = {
      mensual: 'Mensual',
      trimestral: 'Trimestral',
      semestral: 'Semestral',
      anual: 'Anual',
      visita: 'Visita única',
      personalizada: 'Personalizada',
    };
    return labels[tipo] || tipo;
  }

  protected formatEstadoMembresia(estado: string): string {
    const labels: Record<string, string> = {
      activa: 'Activa',
      por_vencer: 'Por vencer',
      vencida: 'Vencida',
      cancelada: 'Cancelada',
      congelada: 'Congelada',
    };
    return labels[estado] || estado;
  }

  protected getEstadoTone(estado: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    switch (estado) {
      case 'activa': return 'success';
      case 'por_vencer': return 'warning';
      case 'vencida': return 'danger';
      case 'cancelada': return 'neutral';
      case 'congelada': return 'info';
      default: return 'neutral';
    }
  }

  protected readonly formatDate = formatDate;
  protected readonly Math = Math;
}