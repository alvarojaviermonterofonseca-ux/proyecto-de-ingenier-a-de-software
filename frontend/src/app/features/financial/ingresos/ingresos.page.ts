import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { FinancialService } from '../financial.service';
import { Pago, PaginatedResponse, FiltrosPago } from '../financial.models';
import { ToastService } from '../../../core/ui/toast.service';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { PaginationComponent } from '../../../shared/pagination.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import type { PageHeaderAction } from '../../../shared/page-header.component';
import { PERIODOS_RAPIDOS, PeriodoRapido, formatDateTime, rangoPeriodo, todayInput } from '../../../core/utils/format';
import { PagoFormComponent } from '../forms/pago-form.component';

interface Column {
  key: string;
  label: string;
  sortable?: boolean;
}

@Component({
  selector: 'app-ingresos-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    EmptyStateComponent,
    IconComponent,
    PaginationComponent,
    StatusBadgeComponent,
    PageHeaderComponent,
    PagoFormComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-container fade-in">
      <app-page-header
        title="Ingresos"
        subtitle="Gestión y seguimiento de pagos recibidos"
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
            <div class="period-bar" role="group" aria-label="Período rápido">
              @for (p of periodos; track p.valor) {
                <button
                  type="button"
                  class="period-chip"
                  [class.period-chip--active]="periodoActivo() === p.valor"
                  [attr.aria-pressed]="periodoActivo() === p.valor"
                  (click)="seleccionarPeriodo(p.valor)"
                >{{ p.etiqueta }}</button>
              }
              <div class="search-box">
                <app-icon name="search" [size]="16" />
                <input
                  type="search"
                  class="input"
                  placeholder="Buscar cliente, referencia o nota"
                  aria-label="Buscar ingresos"
                  [(ngModel)]="filtros.search"
                  name="search"
                />
              </div>
            </div>
            <div class="filters-row">
              <div class="filter-group">
                <label for="fecha_desde">Desde</label>
                <input
                  id="fecha_desde"
                  type="date"
                  class="input"
                  [(ngModel)]="filtros.fecha_desde"
                  (ngModelChange)="periodoActivo.set(null)"
                  name="fecha_desde"
                />
              </div>
              <div class="filter-group">
                <label for="fecha_hasta">Hasta</label>
                <input
                  id="fecha_hasta"
                  type="date"
                  class="input"
                  [(ngModel)]="filtros.fecha_hasta"
                  (ngModelChange)="periodoActivo.set(null)"
                  name="fecha_hasta"
                />
              </div>
              <div class="filter-group">
                <label for="concepto">Concepto</label>
                <select
                  id="concepto"
                  class="input"
                  [(ngModel)]="filtros.concepto"
                  name="concepto"
                >
                  <option value="">Todos</option>
                  <option value="membresia">Membresía</option>
                  <option value="renovacion">Renovación</option>
                  <option value="matricula">Matrícula</option>
                  <option value="entrenamiento_personal">Entrenamiento personal</option>
                  <option value="plan_alimentacion">Plan de alimentación</option>
                  <option value="producto">Producto</option>
                  <option value="otro">Otro</option>
                </select>
              </div>
              <div class="filter-group">
                <label for="estado">Estado</label>
                <select
                  id="estado"
                  class="input"
                  [(ngModel)]="filtros.estado"
                  name="estado"
                >
                  <option value="">Todos</option>
                  <option value="completado">Completado</option>
                  <option value="pendiente">Pendiente</option>
                  <option value="fallido">Fallido</option>
                  <option value="reembolsado">Reembolsado</option>
                </select>
              </div>
              <div class="filter-group">
                <label for="metodo_pago">Método de pago</label>
                <select
                  id="metodo_pago"
                  class="input"
                  [(ngModel)]="filtros.metodo_pago"
                  name="metodo_pago"
                >
                  <option [ngValue]="undefined">Todos</option>
                  @for (mp of metodosPago(); track mp.id) {
                    <option [ngValue]="mp.id">{{ mp.nombre }}</option>
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

        <!-- Tabla de ingresos -->
        <section class="table-card card">
          <div class="table-responsive">
            @if (pagos().length === 0) {
              <app-empty-state
                icon="dollar-sign"
                title="Sin ingresos registrados"
                message="No se encontraron pagos con los filtros actuales."
              />
            } @else {
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Cliente</th>
                    <th>Concepto</th>
                    <th>Tipo de membresía</th>
                    <th>Valor</th>
                    <th>Método</th>
                    <th>Estado</th>
                    <th>Registrado por</th>
                  </tr>
                </thead>
                <tbody>
                  @for (pago of pagos(); track pago.id) {
                    <tr>
                      <td>{{ formatDateTime(pago.fecha_pago) }}</td>
                      <td>
                        <div class="cell-client">
                          <strong>{{ pago.cliente_detalle.nombre }}</strong>
                          <small>{{ pago.cliente_detalle.correo }}</small>
                        </div>
                      </td>
                      <td>
                        <div class="cell-concept">
                          <app-icon [name]="financialService.getIconoConcepto(pago.concepto)" [size]="14" />
                          <span>{{ financialService.getLabelConcepto(pago.concepto) }}</span>
                          @if (pago.concepto_detalle) {
                            <small>{{ pago.concepto_detalle }}</small>
                          }
                        </div>
                      </td>
                      <td>
                        @if (pago.membresia_detalle) {
                          <span>{{ financialService.getLabelTipoMembresia(pago.membresia_detalle.tipo) }}</span>
                        } @else {
                          <small class="muted">—</small>
                        }
                      </td>
                      <td class="cell-value">
                        <strong>{{ financialService.formatearMoneda(pago.valor) }}</strong>
                      </td>
                      <td>
                        <span class="method-badge" [style.background]="getMetodoColor(pago.metodo_pago_detalle.tipo)">
                          {{ pago.metodo_pago_detalle.nombre }}
                        </span>
                      </td>
                      <td>
                        <app-status-badge
                          [label]="financialService.getLabelEstadoPago(pago.estado)"
                          [tone]="getEstadoTone(pago.estado)"
                        />
                      </td>
                      <td>
                        <small>{{ pago.registrado_por_detalle.nombre }}</small>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </div>

          @if (pagination().totalPages > 1) {
            <app-pagination
              [page]="pagination().currentPage"
              [count]="pagination().totalItems"
              [pageSize]="pagination().pageSize"
              (pageChange)="cambiarPagina($event)"
            />
          }
        </section>

        <!-- Resumen de totales -->
        @if (!loading() && estadisticas()) {
          <section class="summary-card card">
            <h3>Resumen del período filtrado</h3>
            <div class="summary-grid">
              <div class="summary-item summary-item--income">
                <span class="summary-label">Ingresos Completados</span>
                <span class="summary-value">{{ financialService.formatearMoneda(estadisticas()!.total_ingresos) }}</span>
              </div>
              <div class="summary-item summary-item--pending">
                <span class="summary-label">Pagos Pendientes</span>
                <span class="summary-value">{{ financialService.formatearMoneda(estadisticas()!.total_pendientes) }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">Transacciones Completadas</span>
                <span class="summary-value">{{ estadisticas()!.count_completados }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">Transacciones Pendientes</span>
                <span class="summary-value">{{ estadisticas()!.count_pendientes }}</span>
              </div>
            </div>

            <div class="summary-breakdown">
              <h4>Por Concepto</h4>
              <div class="breakdown-list">
                @for (item of estadisticas()!.por_concepto; track item.concepto) {
                  <div class="breakdown-item">
                    <span class="breakdown-label">
                      <app-icon [name]="financialService.getIconoConcepto(item.concepto)" [size]="14" />
                      {{ financialService.getLabelConcepto(item.concepto) }}
                    </span>
                    <span class="breakdown-value">{{ financialService.formatearMoneda(item.total) }}</span>
                    <span class="breakdown-count">({{ item.count }})</span>
                  </div>
                }
              </div>

              <h4>Por Método de Pago</h4>
              <div class="breakdown-list">
                @for (item of estadisticas()!.por_metodo; track item.metodo_pago__nombre) {
                  <div class="breakdown-item">
                    <span class="breakdown-label">
                      <span class="method-dot" [style.background]="getMetodoColorByName(item.metodo_pago__nombre)"></span>
                      {{ item.metodo_pago__nombre }}
                    </span>
                    <span class="breakdown-value">{{ financialService.formatearMoneda(item.total) }}</span>
                    <span class="breakdown-count">({{ item.count }})</span>
                  </div>
                }
              </div>
            </div>
          </section>
        }
      }

      <app-pago-form
        [open]="formularioAbierto()"
        (closed)="formularioAbierto.set(false)"
        (saved)="alGuardarPago()"
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
      grid-template-columns: 160px 200px 180px 140px 140px 140px 160px;
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

    .cell-concept {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }

    .cell-concept app-icon {
      color: var(--color-text-muted);
    }

    .cell-concept small {
      color: var(--color-text-muted);
      font-size: 0.75rem;
    }

    .cell-value {
      font-variant-numeric: tabular-nums;
    }

    .method-badge {
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      color: white;
    }

    .pagination-container {
      padding: 1rem 1.5rem;
      border-top: 1px solid var(--color-border);
    }

    .summary-card {
      padding: 1.5rem;
    }

    .summary-card h3 {
      margin: 0 0 1rem;
      font-size: 1rem;
      font-weight: 600;
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--color-border);
    }

    .summary-item {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .summary-item--income .summary-value { color: var(--color-success); }
    .summary-item--pending .summary-value { color: var(--color-warning); }

    .summary-label {
      font-size: 0.75rem;
      color: var(--color-text-muted);
    }

    .summary-value {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--color-text);
    }

    .summary-breakdown h4 {
      margin: 1.5rem 0 0.75rem;
      font-size: 0.875rem;
      font-weight: 600;
      color: var(--color-text);
    }

    .summary-breakdown h4:first-child {
      margin-top: 0;
    }

    .breakdown-list {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .breakdown-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.5rem 0.75rem;
      background: var(--color-bg);
      border-radius: 0.375rem;
      gap: 1rem;
    }

    .breakdown-label {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      color: var(--color-text);
    }

    .breakdown-label app-icon {
      color: var(--color-text-muted);
    }

    .breakdown-value {
      font-size: 0.875rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      color: var(--color-text);
    }

    .breakdown-count {
      font-size: 0.75rem;
      color: var(--color-text-muted);
    }

    .method-dot {
      width: 0.5rem;
      height: 0.5rem;
      border-radius: 50%;
    }

    .period-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
      margin-bottom: 1rem;
    }

    .period-chip {
      border: 1px solid var(--border, #e2e8f0);
      background: var(--surface, #fff);
      color: inherit;
      border-radius: 999px;
      padding: 0.375rem 0.875rem;
      font: inherit;
      font-size: 0.875rem;
      cursor: pointer;
    }

    .period-chip--active {
      background: var(--primary, #2563eb);
      border-color: var(--primary, #2563eb);
      color: #fff;
    }

    .search-box {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-left: auto;
      min-width: 260px;
    }

    .search-box .input {
      flex: 1;
    }

    .muted {
      color: var(--text-muted, #64748b);
    }

    @media (max-width: 768px) {
      .search-box {
        margin-left: 0;
        min-width: 0;
        width: 100%;
      }

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
export class IngresosPage implements OnInit {
  protected readonly financialService = inject(FinancialService);
  protected readonly toast = inject(ToastService);
  protected readonly confirm = inject(ConfirmService);
  protected readonly router = inject(Router);

  protected readonly pagos = signal<Pago[]>([]);
  protected readonly metodosPago = signal<{ id: number; nombre: string; tipo: string }[]>([]);
  protected readonly estadisticas = signal<{
    total_ingresos: number;
    total_pendientes: number;
    count_completados: number;
    count_pendientes: number;
    por_concepto: Array<{ concepto: string; total: string; count: number }>;
    por_metodo: Array<{ metodo_pago__nombre: string; total: string; count: number }>;
  } | null>(null);
  protected readonly loading = signal(false);
  protected readonly loadingStats = signal(false);

  protected readonly periodos = PERIODOS_RAPIDOS;
  protected readonly periodoActivo = signal<PeriodoRapido | null>(null);

  protected filtros: FiltrosPago = {
    search: '',
    fecha_desde: '',
    fecha_hasta: '',
    concepto: '',
    estado: '',
    metodo_pago: undefined,
  };

  protected readonly pagination = signal({
    currentPage: 1,
    totalPages: 1,
    totalItems: 0,
    pageSize: 25,
  });

  protected readonly formularioAbierto = signal(false);

  protected nuevoPago(): void {
    this.formularioAbierto.set(true);
  }

  protected alGuardarPago(): void {
    this.formularioAbierto.set(false);
    this.pagination.update(p => ({ ...p, currentPage: 1 }));
    this.load();
    this.loadEstadisticas();
  }

  protected readonly headerActions: PageHeaderAction[] = [
    {
      label: 'Registrar ingreso',
      icon: 'plus',
      action: () => this.nuevoPago(),
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
    this.loadMetodosPago();
    this.load();
    this.loadEstadisticas();
  }

  protected load(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = {
      ...this.parametrosFiltro(),
      page: this.pagination().currentPage,
      page_size: this.pagination().pageSize,
    };

    this.financialService.getPagos(params).subscribe({
      next: (response: PaginatedResponse<Pago>) => {
        this.pagos.set(response.results);
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
        this.toast.error('Error al cargar ingresos', err.message);
      },
    });
  }

  protected loadEstadisticas(): void {
    this.loadingStats.set(true);
    this.financialService.getEstadisticasPagos(this.parametrosFiltro()).subscribe({
      next: (stats) => {
        this.estadisticas.set(stats);
        this.loadingStats.set(false);
      },
      error: (err) => {
        this.loadingStats.set(false);
        console.error('Error cargando estadísticas:', err);
      },
    });
  }

  protected loadMetodosPago(): void {
    this.financialService.getAllMetodosPago().subscribe({
      next: (metodos) => {
        this.metodosPago.set(metodos.map(m => ({ id: m.id, nombre: m.nombre, tipo: m.tipo })));
      },
    });
  }

  protected aplicarFiltros(): void {
    this.pagination.update(p => ({ ...p, currentPage: 1 }));
    this.load();
    this.loadEstadisticas();
  }

  protected seleccionarPeriodo(periodo: PeriodoRapido): void {
    const rango = rangoPeriodo(periodo);
    this.filtros.fecha_desde = rango.desde;
    this.filtros.fecha_hasta = rango.hasta;
    this.periodoActivo.set(periodo);
    this.aplicarFiltros();
  }

  private parametrosFiltro(): Record<string, string | number> {
    const params: Record<string, string | number> = {};
    const f = this.filtros;
    if (f.search?.trim()) params['search'] = f.search.trim();
    if (f.fecha_desde) params['fecha_desde'] = f.fecha_desde;
    if (f.fecha_hasta) params['fecha_hasta'] = f.fecha_hasta;
    if (f.concepto) params['concepto'] = f.concepto;
    if (f.estado) params['estado'] = f.estado;
    if (f.metodo_pago) params['metodo_pago'] = f.metodo_pago;
    return params;
  }

  protected limpiarFiltros(): void {
    this.periodoActivo.set(null);
    this.filtros.search = '';
    this.filtros.fecha_desde = '';
    this.filtros.fecha_hasta = '';
    this.filtros.concepto = '';
    this.filtros.estado = '';
    this.filtros.metodo_pago = undefined;
    this.aplicarFiltros();
  }

  protected cambiarPagina(page: number): void {
    this.pagination.update(p => ({ ...p, currentPage: page }));
    this.load();
  }

  protected exportar(): void {
    const params = this.parametrosFiltro();

    this.financialService.exportPagos(params).subscribe({
      next: (blob) => {
        this.financialService.guardarArchivo(blob, `ingresos_${todayInput()}.csv`);
        this.toast.success('Exportación completada', 'El archivo CSV se ha descargado');
      },
      error: (err) => {
        this.toast.error('Error al exportar', err.message);
      },
    });
  }

  protected getMetodoColor(tipo: string): string {
    const colores: Record<string, string> = {
      efectivo: '#22c55e',
      transferencia: '#3b82f6',
      tarjeta: '#8b5cf6',
      otro: '#64748b',
    };
    return colores[tipo] || '#64748b';
  }

  protected getMetodoColorByName(nombre: string): string {
    const metodo = this.metodosPago().find(m => m.nombre === nombre);
    return metodo ? this.getMetodoColor(metodo.tipo) : '#64748b';
  }

  protected getEstadoTone(estado: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    switch (estado) {
      case 'completado': return 'success';
      case 'pendiente': return 'warning';
      case 'fallido': return 'danger';
      case 'reembolsado': return 'info';
      default: return 'neutral';
    }
  }

  protected readonly formatDateTime = formatDateTime;
}