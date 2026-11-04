import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-not-found-page',
  standalone: true,
  imports: [RouterLink, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="state-page">
      <span class="state-page__code">404</span>
      <span class="state-page__icon"><app-icon name="search" [size]="34" /></span>
      <h1>No encontramos esta página</h1>
      <p>La dirección cambió o el recurso ya no existe. Vuelve al panel para continuar.</p>
      <div class="state-page__actions">
        <a class="button button--primary" routerLink="/inicio">
          <app-icon name="home" [size]="17" />
          Volver al inicio
        </a>
        <a class="button button--outline" routerLink="/login">
          <app-icon name="log-in" [size]="17" />
          Iniciar sesión
        </a>
      </div>
    </div>
  `,
  styles: [
    `
      :host {
        display: grid;
        min-height: 100vh;
        place-items: center;
        padding: 1.5rem;
      }
      .state-page {
        display: grid;
        max-width: 34rem;
        justify-items: center;
        text-align: center;
      }
      .state-page__code {
        color: var(--gc-border-strong);
        font-size: clamp(5rem, 14vw, 9rem);
        font-weight: 900;
        letter-spacing: -0.08em;
        line-height: 0.85;
      }
      .state-page__icon {
        display: grid;
        width: 4.2rem;
        height: 4.2rem;
        margin: 1.4rem 0 1rem;
        place-items: center;
        border-radius: 1.2rem;
        color: var(--gc-primary);
        background: var(--gc-primary-soft);
      }
      h1 {
        margin: 0 0 0.5rem;
        font-size: 1.65rem;
        letter-spacing: -0.04em;
      }
      p {
        margin: 0 0 1.3rem;
        color: var(--gc-muted);
      }
      .state-page__actions {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.55rem;
        margin-top: 1.4rem;
      }
    `,
  ],
})
export class NotFoundPage {}
