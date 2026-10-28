import { ChangeDetectionStrategy, Component, HostListener, inject } from '@angular/core';

import { ConfirmService } from '../core/ui/confirm.service';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (confirm.state().open) {
      <div class="confirm-backdrop" (click)="onBackdrop($event)">
        <section class="confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
          <span class="confirm__icon" [attr.data-tone]="confirm.state().tone ?? 'danger'">
            <app-icon name="alert" [size]="22" />
          </span>
          <div>
            <h2 id="confirm-title">{{ confirm.state().title }}</h2>
            <p>{{ confirm.state().message }}</p>
          </div>
          <div class="confirm__actions">
            <button class="button button--secondary" type="button" (click)="confirm.cancel()">
              {{ confirm.state().cancelLabel ?? 'Cancelar' }}
            </button>
            <button
              class="button"
              type="button"
              [class.button--danger]="(confirm.state().tone ?? 'danger') === 'danger'"
              [class.button--primary]="confirm.state().tone === 'primary'"
              (click)="confirm.accept()"
            >
              {{ confirm.state().confirmLabel ?? 'Confirmar' }}
            </button>
          </div>
        </section>
      </div>
    }
  `,
  styles: [
    `
      .confirm-backdrop {
        position: fixed;
        z-index: 80;
        inset: 0;
        display: grid;
        place-items: center;
        padding: 1.2rem;
        background: rgb(8 24 16 / 58%);
        backdrop-filter: blur(3px);
      }
      .confirm {
        display: grid;
        width: min(30rem, 100%);
        grid-template-columns: auto 1fr;
        gap: 0.9rem 1rem;
        padding: 1.4rem;
        border: 1px solid var(--gc-border);
        border-radius: 1.1rem;
        background: var(--gc-surface);
        box-shadow: var(--gc-shadow-lg);
      }
      .confirm__icon {
        display: grid;
        width: 2.8rem;
        height: 2.8rem;
        place-items: center;
        border-radius: 0.85rem;
        color: var(--gc-danger);
        background: var(--gc-danger-soft);
      }
      .confirm__icon[data-tone='primary'] {
        color: var(--gc-primary);
        background: var(--gc-primary-soft);
      }
      h2 {
        margin: 0 0 0.3rem;
        font-size: 1.05rem;
      }
      p {
        margin: 0;
        color: var(--gc-muted);
        font-size: 0.86rem;
        line-height: 1.5;
      }
      .confirm__actions {
        display: flex;
        grid-column: 1 / -1;
        justify-content: flex-end;
        gap: 0.55rem;
        margin-top: 0.4rem;
      }
    `,
  ],
})
export class ConfirmDialogComponent {
  protected readonly confirm = inject(ConfirmService);

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.confirm.state().open) {
      this.confirm.cancel();
    }
  }

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.confirm.cancel();
    }
  }
}
