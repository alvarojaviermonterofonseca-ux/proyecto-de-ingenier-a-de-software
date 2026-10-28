import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="badge" [attr.data-tone]="tone()">{{ label() }}</span>`,
  styles: [
    `
      .badge {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.24rem 0.58rem;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 750;
        white-space: nowrap;
      }
      .badge::before {
        width: 0.4rem;
        height: 0.4rem;
        border-radius: 50%;
        background: currentColor;
        content: '';
      }
      [data-tone='success'] { color: #176b42; background: #e7f7ed; }
      [data-tone='danger'] { color: #a13a35; background: #fdeeed; }
      [data-tone='warning'] { color: #836117; background: #fff6dc; }
      [data-tone='info'] { color: #24627d; background: #e9f6fc; }
      [data-tone='neutral'] { color: #5d6b63; background: #eef2ef; }
      [data-tone='accent'] { color: #3b5d0b; background: #edf9d4; }
    `,
  ],
})
export class StatusBadgeComponent {
  readonly label = input.required<string>();
  readonly tone = input<'success' | 'danger' | 'warning' | 'info' | 'neutral' | 'accent'>(
    'neutral',
  );
}
