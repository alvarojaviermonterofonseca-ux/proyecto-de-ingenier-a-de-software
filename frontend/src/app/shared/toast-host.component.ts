import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ToastService } from '../core/ui/toast.service';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-toast-host',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toast-host" aria-live="polite" aria-atomic="false">
      @for (toast of toasts.toasts(); track toast.id) {
        <article class="toast" [attr.data-tone]="toast.tone">
          <span class="toast__icon">
            <app-icon [name]="iconFor(toast.tone)" [size]="18" />
          </span>
          <div class="toast__content">
            <strong>{{ toast.title }}</strong>
            @if (toast.message) {
              <p>{{ toast.message }}</p>
            }
          </div>
          <button
            class="toast__close"
            type="button"
            aria-label="Cerrar notificación"
            (click)="toasts.dismiss(toast.id)"
          >
            <app-icon name="close" [size]="15" />
          </button>
        </article>
      }
    </div>
  `,
  styles: [
    `
      .toast-host {
        position: fixed;
        z-index: 100;
        right: 1.25rem;
        bottom: 1.25rem;
        display: grid;
        width: min(23rem, calc(100vw - 2rem));
        gap: 0.6rem;
        pointer-events: none;
      }
      .toast {
        display: flex;
        align-items: flex-start;
        gap: 0.65rem;
        padding: 0.85rem;
        border: 1px solid var(--gc-border);
        border-left: 4px solid var(--gc-muted);
        border-radius: 0.75rem;
        background: var(--gc-surface);
        box-shadow: var(--gc-shadow);
        pointer-events: auto;
        animation: toast-in 180ms ease;
      }
      .toast[data-tone='success'] { border-left-color: #2c9b61; }
      .toast[data-tone='error'] { border-left-color: var(--gc-danger); }
      .toast[data-tone='warning'] { border-left-color: #c59a2b; }
      .toast[data-tone='info'] { border-left-color: #3a93b6; }
      .toast__icon {
        display: grid;
        width: 1.8rem;
        height: 1.8rem;
        place-items: center;
        flex: none;
        border-radius: 0.55rem;
        color: var(--gc-primary);
        background: var(--gc-primary-soft);
      }
      .toast[data-tone='error'] .toast__icon { color: var(--gc-danger); background: var(--gc-danger-soft); }
      .toast[data-tone='warning'] .toast__icon { color: var(--gc-warning); background: var(--gc-warning-soft); }
      .toast[data-tone='info'] .toast__icon { color: var(--gc-info); background: var(--gc-info-soft); }
      .toast__content {
        min-width: 0;
        flex: 1;
      }
      strong {
        display: block;
        font-size: 0.86rem;
      }
      p {
        margin: 0.18rem 0 0;
        color: var(--gc-muted);
        font-size: 0.8rem;
        line-height: 1.4;
      }
      .toast__close {
        display: grid;
        width: 1.5rem;
        height: 1.5rem;
        padding: 0;
        place-items: center;
        border: 0;
        border-radius: 0.35rem;
        color: var(--gc-muted);
        background: transparent;
      }
      .toast__close:hover {
        background: var(--gc-surface-3);
      }
      @keyframes toast-in {
        from { opacity: 0; transform: translateY(8px); }
      }
    `,
  ],
})
export class ToastHostComponent {
  protected readonly toasts = inject(ToastService);

  protected iconFor(tone: string): string {
    if (tone === 'success') return 'check';
    if (tone === 'error') return 'alert';
    if (tone === 'warning') return 'alert';
    return 'sparkles';
  }
}
