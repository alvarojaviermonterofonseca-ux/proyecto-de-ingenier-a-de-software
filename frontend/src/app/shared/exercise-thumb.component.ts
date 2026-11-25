import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';

import { ExerciseImagesService } from '../core/training/exercise-images.service';

/**
 * Miniatura del ejercicio: la imagen que subió el entrenador o, si no hay,
 * una ilustración generada por código (iniciales sobre fondo degradado).
 */
@Component({
  selector: 'app-exercise-thumb',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="thumb" [style.width.px]="size()" [style.height.px]="size()">
      @if (src(); as url) {
        <img [src]="url" [alt]="'Referencia de ' + name()" loading="lazy" />
      } @else {
        <div class="thumb__placeholder" [style.background]="gradient()" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M6.5 6.5v11M17.5 6.5v11M3 9.5v5M21 9.5v5M6.5 12h11" />
          </svg>
          <span>{{ initials() }}</span>
        </div>
      }
    </div>
  `,
  styles: [
    `
      .thumb { border-radius: 1rem; overflow: hidden; flex-shrink: 0; background: #1f2937; }
      img { width: 100%; height: 100%; object-fit: cover; display: block; }
      .thumb__placeholder {
        width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center;
        justify-content: center; gap: 0.1rem; color: rgba(255, 255, 255, 0.85);
      }
      .thumb__placeholder svg { width: 40%; height: 40%; }
      .thumb__placeholder span { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.04em; }
    `,
  ],
})
export class ExerciseThumbComponent {
  /** Ruta de la API de la imagen (``ejercicios/3/imagen/`` o la del plan). */
  readonly path = input<string | null>(null);
  /** Cambia cuando se reemplaza la imagen, para no mostrar la anterior. */
  readonly version = input('');
  readonly name = input('');
  readonly size = input(64);

  private readonly images = inject(ExerciseImagesService);
  private readonly key = computed(() => (this.path() ? `${this.path()}#${this.version()}` : null));
  protected readonly src = computed(() => this.images.url(this.key()));

  protected readonly initials = computed(() =>
    this.name()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((word) => word[0]?.toUpperCase())
      .join(''),
  );

  protected readonly gradient = computed(() => {
    let hash = 0;
    for (const char of this.name()) hash = (hash * 31 + char.charCodeAt(0)) % 360;
    return `linear-gradient(135deg, hsl(${hash} 45% 32%), hsl(${(hash + 40) % 360} 55% 18%))`;
  });

  constructor() {
    effect(() => {
      const key = this.key();
      const path = this.path();
      if (key && path) this.images.load(key, path);
    });
  }
}
