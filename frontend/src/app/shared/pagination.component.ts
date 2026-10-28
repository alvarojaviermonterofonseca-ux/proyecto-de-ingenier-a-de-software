import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { IconComponent } from './icon.component';

@Component({
  selector: 'app-pagination',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (totalPages() > 1) {
      <nav class="pagination" aria-label="Paginación">
        <p>
          Página <strong>{{ page() }}</strong> de <strong>{{ totalPages() }}</strong>
          <span>· {{ count() }} registros</span>
        </p>
        <div class="pagination__buttons">
          <button
            class="icon-button"
            type="button"
            [disabled]="page() <= 1"
            (click)="go(page() - 1)"
            aria-label="Página anterior"
          >
            <app-icon name="chevron-left" [size]="18" />
          </button>
          <button
            class="icon-button"
            type="button"
            [disabled]="page() >= totalPages()"
            (click)="go(page() + 1)"
            aria-label="Página siguiente"
          >
            <app-icon name="chevron-right" [size]="18" />
          </button>
        </div>
      </nav>
    }
  `,
  styles: [
    `
      .pagination {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding-top: 1rem;
        border-top: 1px solid var(--gc-border);
      }
      p {
        margin: 0;
        color: var(--gc-muted);
        font-size: 0.84rem;
      }
      span {
        margin-left: 0.3rem;
      }
      .pagination__buttons {
        display: flex;
        gap: 0.4rem;
      }
    `,
  ],
})
export class PaginationComponent {
  readonly page = input.required<number>();
  readonly count = input.required<number>();
  readonly pageSize = input(25);
  readonly pageChange = output<number>();
  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.count() / Math.max(1, this.pageSize()))),
  );

  go(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.pageChange.emit(page);
    }
  }
}
