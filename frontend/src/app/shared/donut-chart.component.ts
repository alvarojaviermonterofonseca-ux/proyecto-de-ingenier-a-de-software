import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

interface Arc extends DonutSegment {
  dash: string;
  offset: number;
  percent: number;
}

const RADIUS = 60;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Gráfica de dona en SVG, sin dependencias.
 *
 * Al pasar el cursor o enfocar un segmento (o su fila de la leyenda) el centro
 * muestra su valor y porcentaje; sin selección muestra el total.
 */
@Component({
  selector: 'app-donut-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="donut">
      <svg viewBox="0 0 160 160" role="img" [attr.aria-label]="ariaLabel()" class="donut__svg">
        <circle cx="80" cy="80" [attr.r]="radius" class="donut__track" />
        @for (arc of arcs(); track arc.label) {
          <circle
            cx="80"
            cy="80"
            [attr.r]="radius"
            class="donut__arc"
            [class.donut__arc--dim]="activo() !== null && activo() !== arc.label"
            [attr.stroke]="arc.color"
            [attr.stroke-dasharray]="arc.dash"
            [attr.stroke-dashoffset]="arc.offset"
            transform="rotate(-90 80 80)"
            tabindex="0"
            (mouseenter)="activo.set(arc.label)"
            (mouseleave)="activo.set(null)"
            (focus)="activo.set(arc.label)"
            (blur)="activo.set(null)"
          >
            <title>{{ arc.label }}: {{ arc.value }} ({{ arc.percent }}%)</title>
          </circle>
        }
        <text x="80" y="76" text-anchor="middle" class="donut__value">{{ centro().valor }}</text>
        <text x="80" y="94" text-anchor="middle" class="donut__caption">{{ centro().texto }}</text>
      </svg>
      <ul class="donut__legend">
        @for (arc of arcs(); track arc.label) {
          <li
            [class.is-active]="activo() === arc.label"
            (mouseenter)="activo.set(arc.label)"
            (mouseleave)="activo.set(null)"
          >
            <i [style.background]="arc.color"></i>
            <span class="donut__legend-label">{{ arc.label }}</span>
            <strong>{{ arc.value }}</strong>
            <small>{{ arc.percent }}%</small>
          </li>
        }
      </ul>
    </div>
  `,
  styles: [
    `
      :host { display: block; width: 100%; }
      .donut { display: flex; align-items: center; justify-content: center; gap: 1.5rem; flex-wrap: wrap; }
      .donut__svg { width: 180px; max-width: 100%; height: auto; }
      .donut__track { fill: none; stroke: var(--gc-border); stroke-width: 22; opacity: 0.5; }
      .donut__arc { fill: none; stroke-width: 22; cursor: pointer; transition: opacity 0.15s ease; outline: none; }
      .donut__arc--dim { opacity: 0.3; }
      .donut__value { font-size: 22px; font-weight: 700; fill: var(--gc-text, currentColor); font-family: inherit; }
      .donut__caption { font-size: 10px; fill: var(--gc-muted); font-family: inherit; }
      .donut__legend { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; min-width: 180px; font-size: 0.85rem; }
      .donut__legend li { display: grid; grid-template-columns: 12px 1fr auto auto; align-items: center; gap: 0.5rem; padding: 0.2rem 0.4rem; border-radius: 0.375rem; }
      .donut__legend li.is-active { background: var(--gc-surface-muted, rgba(148, 163, 184, 0.15)); }
      .donut__legend i { width: 12px; height: 12px; border-radius: 3px; }
      .donut__legend small { color: var(--gc-muted); min-width: 2.5rem; text-align: right; }
    `,
  ],
})
export class DonutChartComponent {
  readonly segments = input.required<DonutSegment[]>();
  readonly ariaLabel = input('Gráfica de dona');
  readonly totalLabel = input('Total');

  protected readonly radius = RADIUS;
  protected readonly activo = signal<string | null>(null);

  private readonly total = computed(() =>
    this.segments().reduce((suma, segmento) => suma + Math.max(0, segmento.value), 0),
  );

  protected readonly arcs = computed((): Arc[] => {
    const total = this.total();
    let acumulado = 0;
    return this.segments()
      .filter((segmento) => segmento.value > 0)
      .map((segmento) => {
        const fraccion = total ? segmento.value / total : 0;
        const largo = fraccion * CIRCUMFERENCE;
        const arc: Arc = {
          ...segmento,
          dash: `${largo} ${CIRCUMFERENCE - largo}`,
          offset: -acumulado,
          percent: Math.round(fraccion * 1000) / 10,
        };
        acumulado += largo;
        return arc;
      });
  });

  protected readonly centro = computed(() => {
    const seleccionado = this.arcs().find((arc) => arc.label === this.activo());
    if (seleccionado) {
      return { valor: String(seleccionado.value), texto: `${seleccionado.label} · ${seleccionado.percent}%` };
    }
    return { valor: String(this.total()), texto: this.totalLabel() };
  });
}
