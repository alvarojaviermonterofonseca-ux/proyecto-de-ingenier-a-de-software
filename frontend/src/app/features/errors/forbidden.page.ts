import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-forbidden-page',
  standalone: true,
  imports: [RouterLink, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="state-page fade-in">
      <span class="state-page__icon"><app-icon name="shield" [size]="38" /></span>
      <span class="eyebrow">Acceso restringido</span>
      <h2>Esta sección no está disponible para tu rol</h2>
      <p>
        Tu cuenta no tiene el permiso necesario para ver este recurso. Si crees que
        se trata de un error, contacta al administrador del gimnasio.
      </p>
      <div class="state-page__actions">
        <a class="button button--primary" routerLink="/inicio">
          <app-icon name="home" [size]="17" />
          Ir al inicio
        </a>
        <button class="button button--secondary" type="button" (click)="back()">
          Volver
        </button>
        <a class="button button--outline" routerLink="/login">
          <app-icon name="log-in" [size]="17" />
          Iniciar sesión
        </a>
      </div>
      <p class="state-page__meta">
        Sesión: {{ auth.user()?.correo }} · {{ auth.roleName() ?? 'Sin rol' }}
      </p>
    </div>
  `,
  styles: [
    `
      .state-page {
        display: grid;
        max-width: 40rem;
        margin: 8vh auto;
        justify-items: center;
        padding: 2.5rem 1.5rem;
        text-align: center;
      }
      .state-page__icon {
        display: grid;
        width: 5rem;
        height: 5rem;
        margin-bottom: 1.2rem;
        place-items: center;
        border: 1px solid var(--gc-border);
        border-radius: 1.4rem;
        color: var(--gc-primary);
        background: var(--gc-primary-soft);
      }
      .eyebrow {
        color: var(--gc-primary);
        font-size: 0.7rem;
        font-weight: 850;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }
      h2 {
        margin: 0.5rem 0 0.7rem;
        font-size: clamp(1.5rem, 3vw, 2.15rem);
        letter-spacing: -0.04em;
      }
      p {
        max-width: 32rem;
        margin: 0;
        color: var(--gc-muted);
        line-height: 1.6;
      }
      .state-page__actions {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.55rem;
        margin-top: 1.4rem;
      }
      .state-page__meta {
        margin-top: 1.5rem;
        font-size: 0.75rem;
      }
    `,
  ],
})
export class ForbiddenPage {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected back(): void {
    history.length > 1 ? history.back() : void this.router.navigate(['/inicio']);
  }
}
