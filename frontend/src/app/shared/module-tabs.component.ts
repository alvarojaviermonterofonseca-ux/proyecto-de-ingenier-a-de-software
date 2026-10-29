import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

export interface ModuleTab {
  label: string;
  route: string;
}

@Component({
  selector: 'app-module-tabs',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <nav class="module-tabs" aria-label="Secciones del módulo">
      @for (tab of tabs(); track tab.route) {
        <a
          class="module-tabs__link"
          [routerLink]="tab.route"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: false }"
        >{{ tab.label }}</a>
      }
    </nav>
  `,
  styles: [
    `
      .module-tabs {
        display: flex;
        gap: 1.4rem;
        margin-bottom: 1.35rem;
        overflow-x: auto;
        border-bottom: 1px solid var(--gc-border);
      }
      .module-tabs__link {
        padding: 0.6rem 0;
        border-bottom: 2px solid transparent;
        margin-bottom: -1px;
        color: var(--gc-muted);
        font-size: 0.9rem;
        font-weight: 500;
        text-decoration: none;
        white-space: nowrap;
      }
      .module-tabs__link:hover {
        color: var(--gc-ink);
      }
      .module-tabs__link.active {
        border-bottom-color: var(--gc-primary);
        color: var(--gc-ink);
      }
    `,
  ],
})
export class ModuleTabsComponent {
  readonly tabs = input.required<readonly ModuleTab[]>();
}
