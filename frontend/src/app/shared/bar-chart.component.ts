import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface BarChartSeries {
  name: string;
  color: string;
  values: number[];
}

interface Bar {
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  title: string;
}

const WIDTH = 640;
const HEIGHT = 240;
const MARGIN = { top: 12, right: 8, bottom: 28, left: 56 };

/**
 * Gráfica de barras verticales en SVG, sin dependencias.
 *
 * Admite varias series agrupadas por etiqueta y valores negativos (las barras
 * bajan desde la línea de cero). El valor exacto de cada barra queda como
 * `<title>`, que el navegador muestra al pasar el cursor y leen los lectores
 * de pantalla.
 */
@Component({
  selector: 'app-bar-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      class="bar-chart"
      [attr.viewBox]="'0 0 ' + width + ' ' + height"
      role="img"
      [attr.aria-label]="ariaLabel()"
      preserveAspectRatio="xMidYMid meet"
    >
      @for (tick of geometry().ticks; track tick.value) {
        <line class="bar-chart__grid" [attr.x1]="left" [attr.x2]="width - right" [attr.y1]="tick.y" [attr.y2]="tick.y" />
        <text class="bar-chart__tick" [attr.x]="left - 6" [attr.y]="tick.y + 3" text-anchor="end">{{ tick.label }}</text>
      }
      <line class="bar-chart__zero" [attr.x1]="left" [attr.x2]="width - right" [attr.y1]="geometry().zeroY" [attr.y2]="geometry().zeroY" />
      @for (bar of geometry().bars; track $index) {
        <rect [attr.x]="bar.x" [attr.y]="bar.y" [attr.width]="bar.width" [attr.height]="bar.height" [attr.fill]="bar.color" rx="2">
          <title>{{ bar.title }}</title>
        </rect>
      }
      @for (label of geometry().labels; track label.x) {
        <text class="bar-chart__label" [attr.x]="label.x" [attr.y]="height - 8" text-anchor="middle">{{ label.text }}</text>
      }
    </svg>
    @if (series().length > 1) {
      <div class="bar-chart__legend">
        @for (serie of series(); track serie.name) {
          <span><i [style.background]="serie.color"></i>{{ serie.name }}</span>
        }
      </div>
    }
  `,
  styles: [
    `
      :host { display: block; width: 100%; }
      .bar-chart { display: block; width: 100%; height: auto; }
      .bar-chart__grid { stroke: var(--gc-border); stroke-width: 1; stroke-dasharray: 3 4; opacity: 0.6; }
      .bar-chart__zero { stroke: var(--gc-border-strong); stroke-width: 1; }
      .bar-chart__tick, .bar-chart__label { fill: var(--gc-muted); font-size: 10px; font-family: inherit; }
      .bar-chart__legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 1rem; margin-top: 0.5rem; font-size: 0.8rem; color: var(--gc-muted); }
      .bar-chart__legend span { display: inline-flex; align-items: center; gap: 0.4rem; }
      .bar-chart__legend i { width: 10px; height: 10px; border-radius: 2px; }
    `,
  ],
})
export class BarChartComponent {
  readonly labels = input.required<string[]>();
  readonly series = input.required<BarChartSeries[]>();
  readonly ariaLabel = input('Gráfica de barras');
  /** Da formato a los valores del eje y de los tooltips (p. ej. moneda). */
  readonly formatValue = input<(value: number) => string>((value) => String(value));
  /** Da formato corto a las marcas del eje vertical. */
  readonly formatTick = input<((value: number) => string) | null>(null);

  protected readonly width = WIDTH;
  protected readonly height = HEIGHT;
  protected readonly left = MARGIN.left;
  protected readonly right = MARGIN.right;

  protected readonly geometry = computed(() => {
    const labels = this.labels();
    const series = this.series();
    const format = this.formatValue();
    const formatTick = this.formatTick() ?? format;
    const values = series.flatMap((serie) => serie.values);
    const max = Math.max(0, ...values);
    const min = Math.min(0, ...values);
    const span = max - min || 1;
    const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
    const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
    const toY = (value: number) => MARGIN.top + ((max - value) / span) * plotHeight;
    const zeroY = toY(0);

    const groupWidth = labels.length > 0 ? plotWidth / labels.length : plotWidth;
    const barWidth = Math.max(1, (groupWidth * 0.72) / Math.max(series.length, 1));
    const bars: Bar[] = [];
    labels.forEach((label, index) => {
      const groupStart = MARGIN.left + index * groupWidth + groupWidth * 0.14;
      series.forEach((serie, serieIndex) => {
        const value = serie.values[index] ?? 0;
        const y = toY(value);
        bars.push({
          x: groupStart + serieIndex * barWidth,
          y: Math.min(y, zeroY),
          width: Math.max(1, barWidth - 1),
          height: Math.abs(zeroY - y),
          color: serie.color,
          title: `${label} · ${serie.name}: ${format(value)}`,
        });
      });
    });

    // Con muchas etiquetas se muestra una de cada N para que no se pisen.
    const step = Math.max(1, Math.ceil(labels.length / 12));
    const axisLabels = labels
      .map((text, index) => ({ text, x: MARGIN.left + index * groupWidth + groupWidth / 2, index }))
      .filter((label) => label.index % step === 0);

    const ticks = [max, max - span / 2, min]
      .filter((value, index, all) => all.indexOf(value) === index)
      .map((value) => ({ value, y: toY(value), label: formatTick(value) }));

    return { bars, labels: axisLabels, ticks, zeroY };
  });
}
