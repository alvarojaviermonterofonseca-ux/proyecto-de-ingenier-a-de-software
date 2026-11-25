import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { FinancialService } from '../financial.service';
import { Gasto, PaginatedResponse, FiltrosGasto } from '../financial.models';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { PaginationComponent } from '../../../shared/pagination.component'
import { StatusBadgeComponent } from '../../../shared/status-badge.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import type { PageHeaderAction } from '../../../shared/page-header.component';
import { PERIODOS_RAPIDOS, PeriodoRapido, formatDate, rangoPeriodo, todayInput } from '../../../core/utils/format';
import { AuthService } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { GastoFormComponent } from '../forms/gasto-form.component';

@Component({
  selector: 'app-gastos-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    EmptyStateComponent,
    IconComponent,
    PaginationComponent,
    StatusBadgeComponent,
    PageHeaderComponent,
    GastoFormComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-container fade-in">
      <app-page-header
        title="Gastos"
        subtitle="Registro y control de egresos del gimnasio"
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
                  placeholder="Buscar descripción, referencia u observación"
                  aria-label="Buscar gastos"
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
                <label for="categoria">Categoría</label>
                <select
                  id="categoria"
                  class="input"
                  [(ngModel)]="filtros.categoria"
                  name="categoria"
                >
                  <option [ngValue]="undefined">Todas</option>
                  @for (cat of categoriasGasto(); track cat.id) {
                    <option [ngValue]="cat.id">{{ cat.nombre }}</option>
                  }
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
                  <option value="registrado">Registrado</option>
                  <option value="aprobado">Aprobado</option>
                  <option value="pagado">Pagado</option>
                  <option value="cancelado">Cancelado</option>
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
                <button type="button" class="button button--primary" (click)="nuevoGasto()">
                  <app-icon name="plus" [size]="16" />
                  Nuevo Gasto
                </button>
              </div>
            </div>
          </form>
        </section>

        <!-- Tabla de gastos -->
        <section class="table-card card">
          <div class="table-responsive">
            @if (gastos().length === 0) {
              <app-empty-state
                icon="credit-card"
                title="Sin gastos registrados"
                message="No se encontraron gastos con los filtros actuales."
              />
            } @else {
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Descripción</th>
                    <th>Categoría</th>
                    <th>Valor</th>
                    <th>Método</th>
                    <th>Estado</th>
                    <th>Registrado por</th>
                    @if (puedeEditar()) {
                      <th class="cell-actions-head">Acciones</th>
                    }
                  </tr>
                </thead>
                <tbody>
                  @for (gasto of gastos(); track gasto.id) {
                    <tr>
                      <td>{{ formatDate(gasto.fecha) }}</td>
                      <td>
                        <div class="cell-desc">
                          <strong>{{ gasto.descripcion }}</strong>
                          @if (gasto.referencia) {
                            <small>Ref: {{ gasto.referencia }}</small>
                          }
                        </div>
                      </td>
                      <td>
                        <span class="category-badge" [style.background]="gasto.categoria_detalle.color">
                          <app-icon [name]="getCategoriaIcon(gasto.categoria_detalle.tipo)" [size]="14" />
                          {{ gasto.categoria_detalle.nombre }}
                        </span>
                      </td>
                      <td class="cell-value">
                        <strong>{{ financialService.formatearMoneda(gasto.valor) }}</strong>
                      </td>
                      <td>
                        <span class="method-badge" [style.background]="getMetodoColor(gasto.metodo_pago_detalle.tipo)">
                          {{ gasto.metodo_pago_detalle.nombre }}
                        </span>
                      </td>
                      <td>
                        <app-status-badge
                          [label]="financialService.getLabelEstadoGasto(gasto.estado)"
                          [tone]="getEstadoTone(gasto.estado)"
                        />
                      </td>
                      <td>
                        <small>{{ gasto.registrado_por_detalle.nombre }}</small>
                      </td>
                      @if (puedeEditar()) {
                        <td class="cell-actions">
                          <button
                            type="button"
                            class="icon-button"
                            title="Editar gasto"
                            [attr.aria-label]="'Editar gasto ' + gasto.descripcion"
                            (click)="editarGasto(gasto)"
                          >
                            <app-icon name="edit" [size]="16" />
                          </button>
                          @if (gasto.estado !== 'cancelado') {
                            <button
                              type="button"
                              class="icon-button icon-button--danger"
                              title="Anular gasto"
                              [attr.aria-label]="'Anular gasto ' + gasto.descripcion"
                              (click)="anularGasto(gasto)"
                            >
                              <app-icon name="x" [size]="16" />
                            </button>
                          }
                        </td>
                      }
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

        <!-- Resumen de totales -->
        @if (!loading() && estadisticas()) {
          <section class="summary-card card">
            <h3>Resumen del período filtrado</h3>
            <div class="summary-grid">
              <div class="summary-item summary-item--expense">
                <span class="summary-label">Total Gastos</span>
                <span class="summary-value">{{ financialService.formatearMoneda(estadisticas()!.total_gastos) }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">Transacciones</span>
                <span class="summary-value">{{ estadisticas()!.count }}</span>
              </div>
            </div>

            <div class="summary-breakdown">
              <h4>Por Categoría</h4>
              <div class="breakdown-list">
                @for (item of estadisticas()!.por_categoria; track item.categoria__nombre) {
                  <div class="breakdown-item breakdown-item--clickable" role="button" tabindex="0"
                       title="Ver solo esta categoría"
                       (click)="filtrarCategoria(item.categoria__nombre)"
                       (keydown.enter)="filtrarCategoria(item.categoria__nombre)">
                    <span class="breakdown-label">
                      <span class="category-dot" [style.background]="item.categoria__color"></span>
                      {{ item.categoria__nombre }}
                    </span>
                    <span class="breakdown-value">{{ financialService.formatearMoneda(item.total) }}</span>
                    <span class="breakdown-count">({{ item.count }})</span>
                  </div>
                }
              </div>

              <h4>Por Estado</h4>
              <div class="breakdown-list">
                @for (item of estadisticas()!.por_estado; track item.estado) {
                  <div class="breakdown-item">
                    <span class="breakdown-label">
                      <app-status-badge
                        [label]="financialService.getLabelEstadoGasto(item.estado)"
                        [tone]="getEstadoTone(item.estado)"
                        size="sm"
                      />
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

      <app-gasto-form
        [open]="formularioAbierto()"
        [gasto]="gastoEditando()"
        (closed)="cerrarFormulario()"
        (saved)="alGuardarGasto()"
      />
    </div>
  `,
  styles: [`
    .period-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
      margin-bottom: 1rem;
    }

    .period-chip {
      border: 1px solid var(--color-border, #e2e8f0);
      background: var(--color-surface, #fff);
      color: inherit;
      border-radius: 999px;
      padding: 0.375rem 0.875rem;
      font: inherit;
      font-size: 0.875rem;
      cursor: pointer;
    }

    .period-chip--active {
      background: var(--color-primary, #2563eb);
      border-color: var(--color-primary, #2563eb);
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

    .cell-actions {
      white-space: nowrap;
    }

    .cell-actions-head {
      text-align: right;
    }

    .icon-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2rem;
      height: 2rem;
      border-radius: 0.5rem;
      border: 1px solid var(--color-border, #e2e8f0);
      background: var(--color-surface, #fff);
      color: inherit;
      cursor: pointer;
      margin-left: 0.25rem;
    }

    .icon-button--danger {
      color: #dc2626;
    }

    .breakdown-item--clickable {
      cursor: pointer;
      border-radius: 0.5rem;
    }

    .breakdown-item--clickable:hover,
    .breakdown-item--clickable:focus-visible {
      background: var(--color-surface-muted, rgba(148, 163, 184, 0.12));
    }

    @media (max-width: 768px) {
      .search-box {
        margin-left: 0;
        min-width: 0;
        width: 100%;
      }
    }

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
      grid-template-columns: 120px 250px 160px 140px 140px 140px 160px;
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

    .cell-desc {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }

    .cell-desc strong {
      color: var(--color-text);
    }

    .cell-desc small {
      color: var(--color-text-muted);
      font-size: 0.75rem;
    }

    .category-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      color: white;
    }

    .category-badge app-icon {
      color: white;
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

    .summary-item--expense .summary-value { color: var(--color-danger); }

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

    .category-dot {
      width: 0.5rem;
      height: 0.5rem;
      border-radius: 50%;
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
export class GastosPage implements OnInit {
  protected readonly financialService = inject(FinancialService);
  protected readonly toast = inject(ToastService);

  protected readonly gastos = signal<Gasto[]>([]);
  protected readonly categoriasGasto = signal<Array<{ id: number; nombre: string; tipo: string; color: string }>>([]);
  protected readonly metodosPago = signal<{ id: number; nombre: string; tipo: string }[]>([]);
  protected readonly estadisticas = signal<{
    total_gastos: number;
    count: number;
    por_categoria: Array<{ categoria__nombre: string; categoria__color: string; total: string; count: number }>;
    por_estado: Array<{ estado: string; total: string; count: number }>;
  } | null>(null);
  protected readonly loading = signal(false);
  protected readonly loadingStats = signal(false);

  private readonly auth = inject(AuthService);
  private readonly confirm = inject(ConfirmService);

  protected readonly periodos = PERIODOS_RAPIDOS;
  protected readonly periodoActivo = signal<PeriodoRapido | null>(null);
  protected readonly gastoEditando = signal<Gasto | null>(null);
  protected readonly puedeEditar = computed(
    () => this.auth.isAdmin() || this.auth.hasPermission('gastos:edit'),
  );

  protected filtros: FiltrosGasto = {
    search: '',
    fecha_desde: '',
    fecha_hasta: '',
    categoria: undefined,
    estado: '',
    metodo_pago: undefined,
  };

  protected readonly pagination = signal({
    currentPage: 1,
    totalPages: 1,
    totalItems: 0,
    pageSize: 25,
  });

  protected readonly headerActions: PageHeaderAction[] = [
    {
      label: 'Nuevo Gasto',
      icon: 'plus',
      action: () => this.nuevoGasto(),
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
    this.loadCategorias();
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

    this.financialService.getGastos(params).subscribe({
      next: (response: PaginatedResponse<Gasto>) => {
        this.gastos.set(response.results);
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
        this.toast.error('Error al cargar gastos', err.message);
      },
    });
  }

  protected loadEstadisticas(): void {
    this.loadingStats.set(true);
    this.financialService.getEstadisticasGastos(this.parametrosFiltro()).subscribe({
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

  protected loadCategorias(): void {
    this.financialService.getAllCategoriasGasto().subscribe({
      next: (cats) => {
        this.categoriasGasto.set(cats.map(c => ({
          id: c.id,
          nombre: c.nombre,
          tipo: c.tipo,
          color: c.color,
        })));
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

  private parametrosFiltro(): Record<string, string | number> {
    const params: Record<string, string | number> = {};
    const f = this.filtros;
    if (f.search?.trim()) params['search'] = f.search.trim();
    if (f.fecha_desde) params['fecha_desde'] = f.fecha_desde;
    if (f.fecha_hasta) params['fecha_hasta'] = f.fecha_hasta;
    if (f.categoria) params['categoria'] = f.categoria;
    if (f.estado) params['estado'] = f.estado;
    if (f.metodo_pago) params['metodo_pago'] = f.metodo_pago;
    return params;
  }

  protected seleccionarPeriodo(periodo: PeriodoRapido): void {
    const rango = rangoPeriodo(periodo);
    this.filtros.fecha_desde = rango.desde;
    this.filtros.fecha_hasta = rango.hasta;
    this.periodoActivo.set(periodo);
    this.aplicarFiltros();
  }

  protected filtrarCategoria(nombre: string): void {
    const categoria = this.categoriasGasto().find(c => c.nombre === nombre);
    if (!categoria) return;
    this.filtros.categoria = categoria.id;
    this.aplicarFiltros();
  }

  protected limpiarFiltros(): void {
    this.periodoActivo.set(null);
    this.filtros.search = '';
    this.filtros.fecha_desde = '';
    this.filtros.fecha_hasta = '';
    this.filtros.categoria = undefined;
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

    this.financialService.exportGastos(params).subscribe({
      next: (blob) => {
        this.financialService.guardarArchivo(blob, `gastos_${todayInput()}.csv`);
        this.toast.success('Exportación completada', 'El archivo CSV se ha descargado');
      },
      error: (err) => {
        this.toast.error('Error al exportar', err.message);
      },
    });
  }

  protected readonly formularioAbierto = signal(false);

  protected nuevoGasto(): void {
    this.gastoEditando.set(null);
    this.formularioAbierto.set(true);
  }

  protected editarGasto(gasto: Gasto): void {
    this.gastoEditando.set(gasto);
    this.formularioAbierto.set(true);
  }

  protected async anularGasto(gasto: Gasto): Promise<void> {
    const confirmado = await this.confirm.confirm({
      title: 'Anular gasto',
      message: `El gasto "${gasto.descripcion}" pasará a estado cancelado y dejará de sumar en los reportes. ¿Deseas continuar?`,
      confirmLabel: 'Anular',
      tone: 'danger',
    });
    if (!confirmado) return;
    this.financialService.updateGasto(gasto.id, { estado: 'cancelado' }).subscribe({
      next: () => {
        this.toast.success('Gasto anulado');
        this.load();
        this.loadEstadisticas();
      },
      error: (err) => this.toast.error('No se pudo anular el gasto', err.message),
    });
  }

  protected cerrarFormulario(): void {
    this.formularioAbierto.set(false);
    this.gastoEditando.set(null);
  }

  protected alGuardarGasto(): void {
    this.formularioAbierto.set(false);
    this.gastoEditando.set(null);
    this.pagination.update(p => ({ ...p, currentPage: 1 }));
    this.load();
    this.loadEstadisticas();
  }

  protected getCategoriaIcon(tipo: string): string {
    const iconos: Record<string, string> = {
      arriendo: 'home',
      servicios_publicos: 'zap',
      nomina: 'users',
      mantenimiento: 'wrench',
      equipamiento: 'dumbbell',
      limpieza: 'sparkles',
      publicidad: 'megaphone',
      internet: 'wifi',
      otro: 'package',
    };
    return iconos[tipo] || 'package';
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

  protected getEstadoTone(estado: string): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
    switch (estado) {
      case 'pagado': return 'success';
      case 'aprobado': return 'info';
      case 'registrado': return 'warning';
      case 'cancelado': return 'neutral';
      default: return 'neutral';
    }
  }

  protected readonly formatDate = formatDate;
}