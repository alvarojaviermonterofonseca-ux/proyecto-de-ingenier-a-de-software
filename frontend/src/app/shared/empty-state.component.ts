import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { IconComponent } from './icon.component';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="empty-state">
      <span class="empty-state__icon"><app-icon [name]="icon()" [size]="26" /></span>
      <div>
        <h3>{{ title() }}</h3>
        <p>{{ message() }}</p>
      </div>
      <div class="empty-state__actions"><ng-content /></div>
    </div>
  `,
  styles: [
    `
      .empty-state {
        display: grid;
        justify-items: center;
        gap: 0.85rem;
        padding: 3rem 1.5rem;
        text-align: center;
      }
      .empty-state__icon {
        display: grid;
        width: 3.25rem;
        height: 3.25rem;
        place-items: center;
        border-radius: 1rem;
        color: var(--gc-primary);
        background: var(--gc-primary-soft);
      }
      h3 {
        margin: 0 0 0.3rem;
        font-size: 1.02rem;
      }
      p {
        max-width: 34rem;
        margin: 0;
        color: var(--gc-muted);
        line-height: 1.55;
      }
      .empty-state__actions {
        display: flex;
        gap: 0.6rem;
      }
    `,
  ],
})
export class EmptyStateComponent {
  readonly icon = input('sparkles');
  readonly title = input('Sin datos');
  readonly message = input('Todavía no hay información para mostrar.');
}
