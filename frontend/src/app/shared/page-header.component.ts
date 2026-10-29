import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-page-header',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="page-header">
      <div class="page-header__text">
        @if (eyebrow()) {
          <p class="eyebrow">{{ eyebrow() }}</p>
        }
        <h1>{{ title() }}</h1>
        @if (subtitle()) {
          <p class="page-header__subtitle">{{ subtitle() }}</p>
        }
      </div>
      <div class="page-header__actions">
        <ng-content />
      </div>
    </header>
  `,
  styles: [
    `
      .page-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1.5rem;
        margin-bottom: 1.5rem;
      }
      h1 {
        margin: 0;
        font-size: clamp(1.55rem, 2.5vw, 2.15rem);
        letter-spacing: -0.035em;
      }
      .eyebrow {
        margin: 0 0 0.35rem;
        color: var(--gc-muted);
        font-size: 0.8rem;
        font-weight: 500;
        letter-spacing: 0;
      }
      .page-header__subtitle {
        max-width: 48rem;
        margin: 0.45rem 0 0;
        color: var(--gc-muted);
        line-height: 1.55;
      }
      .page-header__actions {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: 0.6rem;
      }
      @media (max-width: 720px) {
        .page-header {
          flex-direction: column;
        }
        .page-header__actions {
          width: 100%;
          justify-content: flex-start;
        }
      }
    `,
  ],
})
export class PageHeaderComponent {
  readonly eyebrow = input('');
  readonly title = input.required<string>();
  readonly subtitle = input('');
}
