import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  effect,
  inject,
  input,
  output,
} from '@angular/core';
import { DOCUMENT } from '@angular/common';

import { IconComponent } from './icon.component';

@Component({
  selector: 'app-modal',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (open()) {
      <div class="modal-backdrop" (click)="onBackdrop($event)">
        <section
          class="modal"
          [class.modal--wide]="size() === 'wide'"
          [class.modal--narrow]="size() === 'narrow'"
          role="dialog"
          aria-modal="true"
          [attr.aria-label]="title()"
        >
          <header class="modal__header">
            <div>
              <h2>{{ title() }}</h2>
              @if (subtitle()) {
                <p>{{ subtitle() }}</p>
              }
            </div>
            <button class="icon-button" type="button" (click)="closed.emit()" aria-label="Cerrar">
              <app-icon name="close" [size]="19" />
            </button>
          </header>
          <div class="modal__body"><ng-content /></div>
        </section>
      </div>
    }
  `,
  styles: [
    `
      .modal-backdrop {
        position: fixed;
        z-index: 60;
        inset: 0;
        display: grid;
        place-items: center;
        padding: 1.25rem;
        background: rgb(8 24 16 / 55%);
        backdrop-filter: blur(3px);
        animation: fade-in 160ms ease;
      }
      .modal {
        display: flex;
        width: min(42rem, 100%);
        max-height: min(88vh, 58rem);
        flex-direction: column;
        overflow: hidden;
        border: 1px solid var(--gc-border);
        border-radius: 1.25rem;
        background: var(--gc-surface);
        box-shadow: var(--gc-shadow-lg);
        animation: rise-in 180ms ease;
      }
      .modal--wide {
        width: min(62rem, 100%);
      }
      .modal--narrow {
        width: min(32rem, 100%);
      }
      .modal__header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        padding: 1.25rem 1.4rem;
        border-bottom: 1px solid var(--gc-border);
      }
      h2 {
        margin: 0;
        font-size: 1.12rem;
        letter-spacing: -0.02em;
      }
      p {
        margin: 0.3rem 0 0;
        color: var(--gc-muted);
        font-size: 0.88rem;
      }
      .modal__body {
        overflow-y: auto;
        padding: 1.35rem 1.4rem 1.5rem;
      }
      @keyframes fade-in {
        from { opacity: 0; }
      }
      @keyframes rise-in {
        from { opacity: 0; transform: translateY(10px) scale(0.99); }
      }
    `,
  ],
})
export class ModalComponent {
  private readonly document = inject(DOCUMENT);
  readonly open = input(false);
  readonly title = input('');
  readonly subtitle = input('');
  readonly size = input<'normal' | 'wide' | 'narrow'>('normal');
  readonly closed = output<void>();

  constructor() {
    effect(() => {
      this.document.body.classList.toggle('modal-open', this.open());
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.open()) {
      this.closed.emit();
    }
  }

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.closed.emit();
    }
  }
}
