import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiError } from '../../../core/api/api-error';
import { ToastService } from '../../../core/ui/toast.service';
import { todayInput } from '../../../core/utils/format';
import { IconComponent } from '../../../shared/icon.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';
import { FinancialService } from '../financial.service';

type Formato = 'xlsx' | 'pdf' | 'csv';

interface ReporteConfig {
  /** Tipo del reporte en la API (`reportes/<tipo>/`). */
  id: string;
  nombre: string;
  descripcion: string;
  icon: string;
  color: string;
  /** Recurso cuyo listado plano también se exporta en CSV, si aplica. */
  recursoCsv?: string;
  /** A qué fecha del registro se aplica el rango elegido. */
  fechaDe: string;
}

interface RangoFechas {
  fecha_desde: string;
  fecha_hasta: string;
}

const REPORTES: ReporteConfig[] = [
  {
    id: 'financiero',
    nombre: 'Financiero',
    descripcion: 'Ingresos, gastos, ganancia neta y margen; resultado por mes, por concepto, método y categoría.',
    icon: 'dollar-sign',
    color: '#0ea5e9',
    fechaDe: 'fecha del movimiento',
  },
  {
    id: 'ingresos',
    nombre: 'Ingresos',
    descripcion: 'Pagos del período con cliente, concepto, tipo de membresía, método, estado y quién los registró.',
    icon: 'trending-up',
    color: '#22c55e',
    recursoCsv: 'pagos',
    fechaDe: 'fecha del pago',
  },
  {
    id: 'gastos',
    nombre: 'Gastos',
    descripcion: 'Egresos por categoría y en detalle; los anulados se listan pero no suman.',
    icon: 'credit-card',
    color: '#ef4444',
    recursoCsv: 'gastos',
    fechaDe: 'fecha del gasto',
  },
  {
    id: 'asistencia',
    nombre: 'Asistencia',
    descripcion: 'Asistencias por día y por hora, hora pico, clientes distintos y detalle de entradas.',
    icon: 'activity',
    color: '#8b5cf6',
    recursoCsv: 'asistencias',
    fechaDe: 'fecha de entrada',
  },
  {
    id: 'clientes',
    nombre: 'Clientes',
    descripcion: 'Todos los clientes con estado, membresía actual, vencimiento y última asistencia.',
    icon: 'users',
    color: '#ec4899',
    recursoCsv: 'clientes',
    fechaDe: 'clientes nuevos según fecha de registro',
  },
  {
    id: 'membresias',
    nombre: 'Membresías',
    descripcion: 'Membresías vigentes en el período, por tipo y por estado, con su valor.',
    icon: 'id-card',
    color: '#f59e0b',
    recursoCsv: 'membresias',
    fechaDe: 'vigencia de la membresía',
  },
  {
    id: 'crecimiento',
    nombre: 'Crecimiento',
    descripcion: 'Evolución mensual de clientes nuevos y acumulados, membresías vendidas, asistencias e ingresos.',
    icon: 'chart',
    color: '#14b8a6',
    fechaDe: 'mes',
  },
];

function inicioDeMes(): string {
  return `${todayInput().slice(0, 8)}01`;
}

@Component({
  selector: 'app-reportes-page',
  standalone: true,
  imports: [FormsModule, IconComponent, PageHeaderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page-container fade-in">
      <app-page-header
        title="Reportes Administrativos"
        subtitle="Reportes del gimnasio con datos reales, en Excel o PDF, para el período que elijas"
      />

      <section class="reports-grid">
        @for (reporte of reportes; track reporte.id) {
          <article class="report-card" [style.border-left-color]="reporte.color">
            <div class="report-card__header">
              <div class="report-card__icon" [style.background]="reporte.color">
                <app-icon [name]="reporte.icon" [size]="24" />
              </div>
              <div class="report-card__info">
                <h3>{{ reporte.nombre }}</h3>
                <p>{{ reporte.descripcion }}</p>
              </div>
            </div>

            <form class="report-card__params" (ngSubmit)="descargar(reporte)">
              <div class="param-group">
                <label [for]="reporte.id + '-desde'">Desde ({{ reporte.fechaDe }})</label>
                <input
                  [id]="reporte.id + '-desde'"
                  type="date"
                  class="input"
                  name="fecha_desde"
                  [ngModel]="rangos()[reporte.id].fecha_desde"
                  (ngModelChange)="cambiarFecha(reporte.id, 'fecha_desde', $event)"
                />
              </div>
              <div class="param-group">
                <label [for]="reporte.id + '-hasta'">Hasta</label>
                <input
                  [id]="reporte.id + '-hasta'"
                  type="date"
                  class="input"
                  name="fecha_hasta"
                  [ngModel]="rangos()[reporte.id].fecha_hasta"
                  (ngModelChange)="cambiarFecha(reporte.id, 'fecha_hasta', $event)"
                />
              </div>
              @if (rangoInvalido(reporte.id)) {
                <p class="field-error">La fecha final no puede ser anterior a la inicial.</p>
              }

              <div class="param-actions">
                <button
                  type="submit"
                  class="button button--primary"
                  [disabled]="ocupado(reporte.id) || rangoInvalido(reporte.id)"
                >
                  <app-icon name="download" [size]="16" />
                  {{ descargando() === reporte.id + ':xlsx' ? 'Generando...' : 'Excel' }}
                </button>
                <button
                  type="button"
                  class="button button--secondary"
                  [disabled]="ocupado(reporte.id) || rangoInvalido(reporte.id)"
                  (click)="descargar(reporte, 'pdf')"
                >
                  <app-icon name="file-text" [size]="16" />
                  {{ descargando() === reporte.id + ':pdf' ? 'Generando...' : 'PDF' }}
                </button>
                @if (reporte.recursoCsv) {
                  <button
                    type="button"
                    class="button button--outline"
                    title="Listado plano en CSV"
                    [disabled]="ocupado(reporte.id) || rangoInvalido(reporte.id)"
                    (click)="descargar(reporte, 'csv')"
                  >
                    {{ descargando() === reporte.id + ':csv' ? 'Generando...' : 'CSV' }}
                  </button>
                }
              </div>
            </form>
          </article>
        }
      </section>
    </div>
  `,
  styles: [`
    .page-container {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .reports-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr));
      gap: 1.5rem;
    }

    .report-card {
      background: var(--color-surface);
      border-radius: 0.75rem;
      border: 1px solid var(--color-border);
      overflow: hidden;
    }

    .report-card__header {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      padding: 1.5rem;
      border-bottom: 1px solid var(--color-border);
    }

    .report-card__icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 3rem;
      height: 3rem;
      border-radius: 0.75rem;
      color: white;
      flex-shrink: 0;
    }

    .report-card__info h3 {
      margin: 0 0 0.25rem;
      font-size: 1.125rem;
      font-weight: 600;
      color: var(--color-text);
    }

    .report-card__info p {
      margin: 0;
      font-size: 0.875rem;
      color: var(--color-text-muted);
    }

    .report-card__params {
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .param-group {
      display: flex;
      flex-direction: column;
      gap: 0.375rem;
    }

    .param-group label {
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--color-text-muted);
      text-transform: uppercase;
      letter-spacing: 0.025em;
    }

    .param-group .input {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: 0.375rem;
      background: var(--color-bg);
      color: var(--color-text);
      font-size: 0.875rem;
      transition: all 0.15s ease;
    }

    .param-group .input:focus {
      outline: none;
      border-color: var(--color-primary);
      box-shadow: 0 0 0 3px var(--color-primary-focus);
    }

    .param-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      padding-top: 0.5rem;
      border-top: 1px solid var(--color-border);
    }

    .spin {
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    .scheduled-reports {
      padding: 1.5rem;
    }

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
    }

    .section-header h2 {
      margin: 0;
      font-size: 1.125rem;
      font-weight: 600;
    }

    @media (max-width: 768px) {
      .reports-grid {
        grid-template-columns: 1fr;
      }

      .report-card__header {
        flex-direction: column;
        align-items: flex-start;
      }
    }
  `],
})
export class ReportesPage {
  private readonly financialService = inject(FinancialService);
  private readonly toast = inject(ToastService);

  protected readonly reportes = REPORTES;
  protected readonly descargando = signal<string | null>(null);
  protected readonly rangos = signal<Record<string, RangoFechas>>(
    Object.fromEntries(
      REPORTES.map((reporte) => [
        reporte.id,
        { fecha_desde: inicioDeMes(), fecha_hasta: todayInput() },
      ]),
    ),
  );

  protected cambiarFecha(id: string, campo: keyof RangoFechas, valor: string): void {
    this.rangos.update((rangos) => ({
      ...rangos,
      [id]: { ...rangos[id], [campo]: valor ?? '' },
    }));
  }

  protected rangoInvalido(id: string): boolean {
    const { fecha_desde, fecha_hasta } = this.rangos()[id];
    return Boolean(fecha_desde && fecha_hasta && fecha_hasta < fecha_desde);
  }

  protected ocupado(id: string): boolean {
    return this.descargando()?.startsWith(`${id}:`) ?? false;
  }

  protected descargar(reporte: ReporteConfig, formato: Formato = 'xlsx'): void {
    if (this.rangoInvalido(reporte.id) || this.ocupado(reporte.id)) {
      return;
    }
    const rango = this.rangos()[reporte.id];
    const peticion =
      formato === 'csv' && reporte.recursoCsv
        ? this.financialService.exportar(reporte.recursoCsv, { ...rango })
        : this.financialService.descargarReporte(reporte.id, formato === 'pdf' ? 'pdf' : 'xlsx', rango);
    this.descargando.set(`${reporte.id}:${formato}`);
    peticion.subscribe({
      next: (blob) => {
        this.descargando.set(null);
        const periodo = [rango.fecha_desde, rango.fecha_hasta].filter(Boolean).join('_a_');
        this.financialService.guardarArchivo(
          blob,
          `reporte_${reporte.id}_${periodo || todayInput()}.${formato}`,
        );
        this.toast.success('Reporte descargado', `${reporte.nombre} (${formato.toUpperCase()})`);
      },
      error: (error: unknown) => {
        this.descargando.set(null);
        this.toast.error(
          'No se pudo generar el reporte',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }
}
