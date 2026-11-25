import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { FinancialService } from '../financial.service';
import { DashboardFinancieroData, MetricasClientes, MetricasAsistencias, MetricasFinancieras, MetricasMembresias, Alerta } from '../financial.models';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { BarChartComponent, BarChartSeries } from '../../../shared/bar-chart.component';
import { DonutChartComponent, DonutSegment } from '../../../shared/donut-chart.component';
import { StatusBadgeComponent } from '../../../shared/status-badge.component';
import { formatCurrency, formatNumber } from '../../../core/utils/format';

interface MetricCard {
  label: string;
  value: string | number;
  subtitle: string;
  icon: string;
  trend?: { value: number; label: string; positive: boolean };
  color?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
}

@Component({
  selector: 'app-financial-dashboard-page',
  standalone: true,
  imports: [
    CommonModule,
    EmptyStateComponent,
    IconComponent,
    StatusBadgeComponent,
    BarChartComponent,
    DonutChartComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="dashboard-page fade-in">
      @if (loading()) {
        <div class="skeleton-grid">
          @for (item of [1,2,3,4,5,6,7,8]; track item) {
            <div class="skeleton-card">
              <div class="skeleton skeleton--title"></div>
              <div class="skeleton skeleton--value"></div>
              <div class="skeleton skeleton--subtitle"></div>
            </div>
          }
        </div>
      } @else if (error()) {
        <div class="notice notice--error" role="alert">
          <app-icon name="alert" [size]="18" />
          <span>{{ error() }}</span>
          <button class="link-button" type="button" (click)="load()">Reintentar</button>
        </div>
      } @else {
        <!-- Tarjetas de métricas principales -->
        <section class="metrics-grid" aria-label="Métricas principales">
          @for (metric of mainMetrics(); track metric.label) {
            <article class="metric-card" [class]="metric.color ? 'metric-card--' + metric.color : ''">
              <div class="metric-card__header">
                <span class="metric-card__label">{{ metric.label }}</span>
                <span class="metric-card__icon" [style.color]="metricColor(metric.color)">
                  <app-icon [name]="metric.icon" [size]="20" />
                </span>
              </div>
              <p class="metric-card__value">{{ metric.value }}</p>
              <p class="metric-card__subtitle">{{ metric.subtitle }}</p>
              @if (metric.trend) {
                <div class="metric-card__trend" [class.positive]="metric.trend.positive" [class.negative]="!metric.trend.positive">
                  <app-icon [name]="metric.trend.positive ? 'trending-up' : 'trending-down'" [size]="12" />
                  <span>{{ metric.trend.value | number:'1.1-1' }}%</span>
                  <small>{{ metric.trend.label }}</small>
                </div>
              }
            </article>
          }
        </section>

        <!-- Período de las gráficas -->
        <section class="period-toolbar" aria-label="Período de las gráficas">
          <label>
            <span>Series mensuales</span>
            <select class="input" [value]="meses()" (change)="cambiarMeses($any($event.target).value)" [disabled]="recargando()">
              @for (opcion of opcionesMeses; track opcion) {
                <option [value]="opcion">Últimos {{ opcion }} meses</option>
              }
            </select>
          </label>
          <label>
            <span>Asistencias diarias</span>
            <select class="input" [value]="dias()" (change)="cambiarDias($any($event.target).value)" [disabled]="recargando()">
              @for (opcion of opcionesDias; track opcion) {
                <option [value]="opcion">Últimos {{ opcion }} días</option>
              }
            </select>
          </label>
          @if (recargando()) {
            <span class="period-toolbar__status" role="status">Actualizando gráficas…</span>
          }
        </section>

        <!-- Gráficas principales -->
        <div class="charts-grid" [class.is-refreshing]="recargando()">
          <!-- Ingresos vs Gastos -->
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Ingresos vs Gastos ({{ meses() }} meses)</h2>
              <p class="chart-card__description">Comparativa mensual de ingresos, gastos y ganancia neta</p>
            </header>
            <div class="chart-card__content">
              <app-bar-chart
                [ariaLabel]="'Ingresos y gastos de los últimos ' + meses() + ' meses'"
                [labels]="etiquetasMeses()"
                [series]="serieIngresosGastos()"
                [formatValue]="formatCurrency"
                [formatTick]="formatoCompacto"
              />
            </div>
          </section>

          <!-- Ganancias mensuales -->
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Ganancia Neta Mensual</h2>
              <p class="chart-card__description">Evolución de la ganancia neta en los últimos {{ meses() }} meses</p>
            </header>
            <div class="chart-card__content">
              <app-bar-chart
                [ariaLabel]="'Ganancia neta de los últimos ' + meses() + ' meses'"
                [labels]="etiquetasMeses()"
                [series]="serieGanancia()"
                [formatValue]="formatCurrency"
                [formatTick]="formatoCompacto"
              />
            </div>
          </section>

          <!-- Asistencias por día -->
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Asistencias por Día ({{ dias() }} días)</h2>
              <p class="chart-card__description">Volumen de asistencias diarias de los últimos {{ dias() }} días</p>
            </header>
            <div class="chart-card__content">
              <app-bar-chart
                [ariaLabel]="'Asistencias por día en los últimos ' + dias() + ' días'"
                [labels]="etiquetasDias()"
                [series]="serieAsistencias()"
              />
            </div>
          </section>

          <!-- Crecimiento de clientes -->
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Crecimiento de Clientes ({{ meses() }} meses)</h2>
              <p class="chart-card__description">Nuevos clientes registrados por mes</p>
            </header>
            <div class="chart-card__content">
              <app-bar-chart
                [ariaLabel]="'Clientes nuevos por mes en los últimos ' + meses() + ' meses'"
                [labels]="etiquetasMeses()"
                [series]="serieClientes()"
              />
            </div>
          </section>

          <!-- Distribución de membresías -->
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Distribución de Membresías</h2>
              <p class="chart-card__description">Membresías activas por tipo</p>
            </header>
            <div class="chart-card__content">
              @if (segmentosMembresias().length > 0) {
                <app-donut-chart
                  ariaLabel="Membresías activas por tipo"
                  totalLabel="Membresías activas"
                  [segments]="segmentosMembresias()"
                />
              } @else {
                <app-empty-state icon="id-card" title="Sin datos" message="No hay membresías activas" />
              }
            </div>
          </section>

          <!-- Clientes activos vs inactivos -->
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Clientes Activos vs Inactivos</h2>
              <p class="chart-card__description">Distribución de clientes por estado de membresía</p>
            </header>
            <div class="chart-card__content">
              @if (segmentosClientes().length > 0) {
                <app-donut-chart
                  ariaLabel="Clientes activos frente a inactivos"
                  totalLabel="Clientes registrados"
                  [segments]="segmentosClientes()"
                />
              } @else {
                <app-empty-state icon="users" title="Sin datos" message="No hay información de clientes" />
              }
            </div>
          </section>
        </div>

        <!-- Horarios de asistencia y alertas -->
        <div class="bottom-grid">
          <section class="chart-card">
            <header class="chart-card__header">
              <h2>Horarios de Mayor Afluencia</h2>
              <p class="chart-card__description">Distribución de asistencias por hora (últimos 30 días)</p>
            </header>
            <div class="chart-card__content">
              @if (dashboard()?.graficas?.horarios_asistencia?.length) {
                <div class="bar-chart-horizontal">
                  @for (hora of dashboard()!.graficas.horarios_asistencia; track hora.hora) {
                    <div class="bar-row">
                      <span class="bar-label">{{ hora.hora }}</span>
                      <div class="bar-track">
                        <div
                          class="bar-fill"
                          [style.width.%]="getBarWidth(hora.total)"
                          [style.background]="getBarColor(hora.hora)"
                        ></div>
                      </div>
                      <span class="bar-value">{{ hora.total }}</span>
                    </div>
                  }
                </div>
              } @else {
                <app-empty-state icon="clock" title="Sin datos" message="No hay asistencias recientes" />
              }
            </div>
          </section>

          <section class="card">
            <header class="card__header">
              <div>
                <h2>Alertas Recientes</h2>
                <p>Alertas administrativas sin leer</p>
              </div>
              <a class="link-button" routerLink="/financiero/alertas">Ver todas</a>
            </header>

            @if (alertasRecientes().length === 0) {
              <app-empty-state icon="bell" title="Todo tranquilo" message="No hay alertas pendientes" />
            } @else {
              <ul class="alert-list">
                @for (alerta of alertasRecientes(); track alerta.id) {
                  <li class="alert-item" [class]="'alert-item--' + alerta.prioridad">
                    <div class="alert-item__icon" [style.background]="financialService.getColorPrioridadAlerta(alerta.prioridad)">
                      <app-icon [name]="getAlertaIcon(alerta.tipo)" [size]="16" />
                    </div>
                    <div class="alert-item__content">
                      <strong>{{ alerta.titulo }}</strong>
                      <p>{{ alerta.mensaje }}</p>
                      <span class="alert-item__meta">
                        <app-icon name="clock" [size]="12" />
                        {{ formatRelativeTime(alerta.created_at) }}
                      </span>
                    </div>
                    <app-status-badge
                      [label]="financialService.getLabelPrioridad(alerta.prioridad)"
                      [tone]="getPrioridadTone(alerta.prioridad)"
                    />
                  </li>
                }
              </ul>
            }
          </section>
        </div>
      }
    </div>
  `,
  styles: [`
    .dashboard-page {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .skeleton-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1rem;
    }

    .skeleton-card {
      padding: 1.5rem;
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
    }

    .skeleton {
      background: linear-gradient(90deg, var(--color-border) 25%, var(--color-bg) 50%, var(--color-border) 75%);
      background-size: 200% 100%;
      animation: skeleton-loading 1.5s infinite;
      border-radius: 0.25rem;
    }

    .skeleton--title { height: 0.75rem; width: 60%; margin-bottom: 0.75rem; }
    .skeleton--value { height: 2rem; width: 40%; margin-bottom: 0.5rem; }
    .skeleton--subtitle { height: 0.75rem; width: 80%; }

    @keyframes skeleton-loading {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
    }

    .metric-card {
      padding: 1.5rem;
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }

    .metric-card:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
    }

    .metric-card--primary { border-left: 4px solid var(--color-primary); }
    .metric-card--success { border-left: 4px solid var(--color-success); }
    .metric-card--warning { border-left: 4px solid var(--color-warning); }
    .metric-card--danger { border-left: 4px solid var(--color-danger); }
    .metric-card--info { border-left: 4px solid var(--color-info); }

    .metric-card__header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.5rem;
    }

    .metric-card__label {
      font-size: 0.875rem;
      font-weight: 500;
      color: var(--color-text-muted);
    }

    .metric-card__icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 0.5rem;
      background: var(--color-bg);
    }

    .metric-card__value {
      font-size: 2rem;
      font-weight: 700;
      color: var(--color-text);
      margin: 0.25rem 0;
      line-height: 1.2;
    }

    .metric-card__subtitle {
      font-size: 0.75rem;
      color: var(--color-text-muted);
      margin: 0;
    }

    .metric-card__trend {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      margin-top: 0.75rem;
      font-size: 0.75rem;
      font-weight: 600;
    }

    .metric-card__trend.positive { color: var(--color-success); }
    .metric-card__trend.negative { color: var(--color-danger); }

    .period-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: 1rem;
      margin: 0.5rem 0 1rem;
    }

    .period-toolbar label {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      font-size: 0.8rem;
      color: var(--gc-muted);
    }

    .period-toolbar select {
      min-width: 190px;
    }

    .period-toolbar__status {
      font-size: 0.85rem;
      color: var(--gc-muted);
    }

    .charts-grid.is-refreshing {
      opacity: 0.6;
      transition: opacity 0.2s ease;
    }

    .charts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 1.5rem;
    }

    .chart-card,
    .card {
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
      overflow: hidden;
    }

    .chart-card__header,
    .card__header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--color-border);
      gap: 1rem;
    }

    .chart-card__header h2,
    .card__header h2 {
      margin: 0;
      font-size: 1rem;
      font-weight: 600;
      color: var(--color-text);
    }

    .chart-card__description {
      margin: 0.25rem 0 0;
      font-size: 0.75rem;
      color: var(--color-text-muted);
    }

    .chart-card__content {
      padding: 1.5rem;
      min-height: 200px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1rem;
    }

    .chart-placeholder {
      color: var(--color-text-muted);
      opacity: 0.5;
    }

    .chart-placeholder-text {
      font-size: 0.875rem;
      color: var(--color-text-muted);
      margin: 0;
    }

    .chart-legend {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      justify-content: center;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      font-size: 0.75rem;
      color: var(--color-text-muted);
    }

    .legend-color {
      width: 0.75rem;
      height: 0.75rem;
      border-radius: 0.125rem;
    }

    .donut-placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--color-text-muted);
      opacity: 0.5;
    }

    .donut-legend {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      justify-content: center;
    }

    .donut-legend li {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      font-size: 0.75rem;
      color: var(--color-text);
    }

    .legend-dot {
      width: 0.625rem;
      height: 0.625rem;
      border-radius: 50%;
    }

    .bottom-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 1.5rem;
    }

    .bar-chart-horizontal {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      width: 100%;
    }

    .bar-row {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .bar-label {
      width: 50px;
      font-size: 0.75rem;
      font-variant-numeric: tabular-nums;
      color: var(--color-text-muted);
    }

    .bar-track {
      flex: 1;
      height: 1.25rem;
      background: var(--color-bg);
      border-radius: 9999px;
      overflow: hidden;
      min-width: 0;
    }

    .bar-fill {
      height: 100%;
      border-radius: 9999px;
      transition: width 0.3s ease;
    }

    .bar-value {
      width: 50px;
      font-size: 0.75rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      color: var(--color-text);
      text-align: right;
    }

    .alert-list {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .alert-item {
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      padding: 1rem;
      background: var(--color-bg);
      border-radius: 0.5rem;
      border: 1px solid var(--color-border);
      transition: all 0.15s ease;
    }

    .alert-item:hover {
      border-color: var(--color-border-strong);
    }

    .alert-item--critica { border-left: 3px solid var(--color-danger); }
    .alert-item--alta { border-left: 3px solid var(--color-warning); }
    .alert-item--media { border-left: 3px solid var(--color-info); }
    .alert-item--baja { border-left: 3px solid var(--color-text-muted); }

    .alert-item__icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 2rem;
      height: 2rem;
      border-radius: 0.375rem;
      color: white;
      flex-shrink: 0;
    }

    .alert-item__content {
      flex: 1;
      min-width: 0;
    }

    .alert-item__content strong {
      display: block;
      font-size: 0.875rem;
      color: var(--color-text);
      margin-bottom: 0.25rem;
    }

    .alert-item__content p {
      margin: 0 0 0.375rem;
      font-size: 0.75rem;
      color: var(--color-text-muted);
      line-height: 1.4;
    }

    .alert-item__meta {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.625rem;
      color: var(--color-text-muted);
    }

    @media (max-width: 768px) {
      .charts-grid,
      .bottom-grid {
        grid-template-columns: 1fr;
      }
    }
  `],
})
export class FinancialDashboardPage implements OnInit {
  protected readonly financialService = inject(FinancialService);
  protected readonly toast = inject(ToastService);

  protected readonly dashboard = signal<DashboardFinancieroData | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly alertasNoLeidas = signal(0);

  protected readonly opcionesMeses = [3, 6, 12, 24];
  protected readonly opcionesDias = [7, 14, 30, 90];
  protected readonly meses = signal(12);
  protected readonly dias = signal(30);
  protected readonly recargando = signal(false);

  ngOnInit(): void {
    this.load();
  }

  protected cambiarMeses(valor: string): void {
    this.meses.set(Number(valor));
    this.load(true);
  }

  protected cambiarDias(valor: string): void {
    this.dias.set(Number(valor));
    this.load(true);
  }

  /** ``soloGraficas`` recarga sin ocultar el tablero con el esqueleto. */
  protected load(soloGraficas = false): void {
    if (soloGraficas && this.dashboard()) {
      this.recargando.set(true);
    } else {
      this.loading.set(true);
    }
    this.error.set(null);
    this.financialService.getDashboard({ meses: this.meses(), dias: this.dias() }).subscribe({
      next: (data) => {
        this.dashboard.set(data);
        this.loading.set(false);
        this.recargando.set(false);
        this.alertasNoLeidas.set(data.alertas_recientes.length);
      },
      error: (err) => {
        this.loading.set(false);
        this.recargando.set(false);
        this.error.set(err.message || 'No se pudo cargar el dashboard.');
        this.toast.error('Error al cargar dashboard', err.message);
      },
    });
  }

  protected readonly segmentosMembresias = computed((): DonutSegment[] =>
    (this.dashboard()?.graficas.distribucion_membresias ?? []).map((item) => ({
      label: this.formatTipoMembresia(item.tipo),
      value: item.count,
      color: this.getTipoColor(item.tipo),
    })),
  );

  protected readonly segmentosClientes = computed((): DonutSegment[] => {
    const clientes = this.dashboard()?.metricas_clientes;
    if (!clientes || clientes.activos + clientes.inactivos === 0) return [];
    return [
      { label: 'Activos', value: clientes.activos, color: '#22c55e' },
      { label: 'Inactivos', value: clientes.inactivos, color: '#64748b' },
    ];
  });

  private static readonly MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  /** Marcas del eje en miles o millones para que quepan. */
  protected readonly formatoCompacto = (valor: number): string => {
    const abs = Math.abs(valor);
    if (abs >= 1_000_000) return `$${(valor / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `$${Math.round(valor / 1_000)}k`;
    return `$${Math.round(valor)}`;
  };

  private readonly ingresosVsGastos = computed(() => this.dashboard()?.graficas.ingresos_vs_gastos ?? []);

  protected readonly etiquetasMeses = computed(() =>
    this.ingresosVsGastos().map((punto) => {
      const [anio, mes] = punto.mes.split('-');
      return `${FinancialDashboardPage.MESES[Number(mes) - 1]} ${anio.slice(2)}`;
    }),
  );

  protected readonly serieIngresosGastos = computed((): BarChartSeries[] => [
    { name: 'Ingresos', color: '#22c55e', values: this.ingresosVsGastos().map((punto) => punto.ingresos) },
    { name: 'Gastos', color: '#ef4444', values: this.ingresosVsGastos().map((punto) => punto.gastos) },
  ]);

  protected readonly serieGanancia = computed((): BarChartSeries[] => [
    { name: 'Ganancia neta', color: '#3b82f6', values: this.ingresosVsGastos().map((punto) => punto.ganancia) },
  ]);

  protected readonly etiquetasDias = computed(() =>
    (this.dashboard()?.graficas.asistencias_por_dia ?? []).map((punto) => {
      const [, mes, dia] = punto.fecha.split('-');
      return `${dia}/${mes}`;
    }),
  );

  protected readonly serieAsistencias = computed((): BarChartSeries[] => [
    {
      name: 'Asistencias',
      color: '#8b5cf6',
      values: (this.dashboard()?.graficas.asistencias_por_dia ?? []).map((punto) => punto.total),
    },
  ]);

  protected readonly serieClientes = computed((): BarChartSeries[] => [
    {
      name: 'Clientes nuevos',
      color: '#ec4899',
      values: (this.dashboard()?.graficas.crecimiento_clientes ?? []).map((punto) => punto.nuevos),
    },
  ]);

  /**
   * Variación real frente al mes anterior, tomada de la serie mensual.
   * Sin base de comparación (mes anterior en cero) no se muestra tendencia.
   */
  private tendencia(
    campo: 'ingresos' | 'gastos' | 'ganancia',
    subirEsBueno: boolean,
  ): MetricCard['trend'] {
    const serie = this.ingresosVsGastos();
    if (serie.length < 2) return undefined;
    const actual = serie[serie.length - 1][campo];
    const anterior = serie[serie.length - 2][campo];
    if (!anterior) return undefined;
    const variacion = ((actual - anterior) / Math.abs(anterior)) * 100;
    return {
      value: variacion,
      label: 'vs mes anterior',
      positive: subirEsBueno ? variacion >= 0 : variacion <= 0,
    };
  }

  private mesAnterior(campo: 'ingresos' | 'gastos'): string {
    const serie = this.ingresosVsGastos();
    return serie.length < 2 ? 'Sin mes anterior' : `Mes anterior: ${formatCurrency(serie[serie.length - 2][campo])}`;
  }

  protected readonly mainMetrics = computed((): MetricCard[] => {
    const d = this.dashboard();
    if (!d) return [];

    return [
      {
        label: 'Ingresos del Mes',
        value: formatCurrency(d.metricas_financieras.ingresos.mes),
        subtitle: this.mesAnterior('ingresos'),
        icon: 'dollar-sign',
        color: 'success',
        trend: this.tendencia('ingresos', true),
      },
      {
        label: 'Gastos del Mes',
        value: formatCurrency(d.metricas_financieras.gastos.mes),
        subtitle: this.mesAnterior('gastos'),
        icon: 'credit-card',
        color: 'danger',
        trend: this.tendencia('gastos', false),
      },
      {
        label: 'Ganancia Neta Mes',
        value: formatCurrency(d.metricas_financieras.ganancia_neta.mes),
        subtitle: `Margen: ${d.metricas_financieras.ingresos.mes > 0 ? ((d.metricas_financieras.ganancia_neta.mes / d.metricas_financieras.ingresos.mes) * 100).toFixed(1) : 0}%`,
        icon: 'trending-up',
        color: d.metricas_financieras.ganancia_neta.mes >= 0 ? 'success' : 'danger',
        trend: this.tendencia('ganancia', true),
      },
      {
        label: 'Clientes Activos',
        value: d.metricas_clientes.activos,
        subtitle: `${d.metricas_clientes.total_registrados} totales`,
        icon: 'users',
        color: 'primary',
      },
      {
        label: 'Asistencias Hoy',
        value: d.metricas_asistencias.hoy,
        subtitle: `Promedio: ${d.metricas_asistencias.promedio_diario}/día`,
        icon: 'clock',
        color: 'info',
      },
      {
        label: 'Membresías por Vencer',
        value: d.metricas_membresias.por_vencer,
        subtitle: `${d.metricas_membresias.vencidas} vencidas`,
        icon: 'alert-triangle',
        color: d.metricas_membresias.por_vencer > 0 ? 'warning' : 'success',
      },
      {
        label: 'Pagos Pendientes',
        value: formatCurrency(d.metricas_financieras.ingresos.pendientes_mes),
        subtitle: `${d.metricas_financieras.ingresos.pendientes_dia} hoy`,
        icon: 'clock',
        color: 'warning',
      },
      {
        label: 'Alertas No Leídas',
        value: this.alertasNoLeidas(),
        subtitle: 'Requieren atención',
        icon: 'bell',
        color: this.alertasNoLeidas() > 0 ? 'danger' : 'success',
      },
    ];
  });

  protected readonly alertasRecientes = computed(() => this.dashboard()?.alertas_recientes ?? []);

  protected readonly membresiaTipoEntries = computed(() => {
    const d = this.dashboard();
    if (!d?.metricas_membresias?.por_tipo) return [];
    return Object.entries(d.metricas_membresias.por_tipo).map(([key, value]) => ({ key, value }));
  });

  protected getTipoColor(tipo: string): string {
    const colores: Record<string, string> = {
      mensual: '#3b82f6',
      trimestral: '#8b5cf6',
      semestral: '#06b6d4',
      anual: '#22c55e',
      visita: '#f59e0b',
      personalizada: '#ec4899',
    };
    return colores[tipo] || '#64748b';
  }

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

  protected getBarWidth(total: number): number {
    const d = this.dashboard();
    if (!d?.graficas?.horarios_asistencia?.length) return 0;
    const max = Math.max(...d.graficas.horarios_asistencia.map(h => h.total));
    return max > 0 ? (total / max) * 100 : 0;
  }

  protected getBarColor(hora: string): string {
    const h = parseInt(hora, 10);
    if (h >= 6 && h <= 9) return '#3b82f6'; // Mañana
    if (h >= 12 && h <= 14) return '#22c55e'; // Mediodía
    if (h >= 17 && h <= 20) return '#f59e0b'; // Tarde
    return '#64748b';
  }

  protected keys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj);
  }

  protected metricColor(color: string | undefined): string {
    const colores: Record<string, string> = {
      primary: '#3b82f6',
      success: '#22c55e',
      warning: '#f59e0b',
      danger: '#ef4444',
      info: '#6366f1',
    };
    return color ? colores[color] || '#64748b' : '#64748b';
  }

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

  protected readonly formatCurrency = formatCurrency;
}