import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { ModuleTabsComponent, type ModuleTab } from '../../shared/module-tabs.component';

const TABS: readonly (ModuleTab & { permission: string; adminOnly?: boolean })[] = [
  { label: 'Usuarios', route: '/autorizados/usuarios', permission: 'usuarios:view' },
  {
    label: 'Roles y permisos',
    route: '/autorizados/seguridad/roles',
    permission: 'roles:view',
  },
  {
    label: 'Catálogo de permisos',
    route: '/autorizados/seguridad/permisos',
    permission: 'permisos:view',
  },
  {
    label: 'Asignaciones',
    route: '/autorizados/seguridad/asignaciones',
    permission: 'usuarios:view',
  },
];

@Component({
  selector: 'app-authorized-layout',
  standalone: true,
  imports: [RouterOutlet, ModuleTabsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-module-tabs [tabs]="tabs()" />
    <router-outlet />
  `,
})
export class AuthorizedLayout {
  private readonly auth = inject(AuthService);
  protected readonly tabs = computed<ModuleTab[]>(() =>
    TABS.filter(
      (tab) => this.auth.hasPermission(tab.permission) && (!tab.adminOnly || this.auth.isAdmin()),
    ).map(({ label, route }) => ({
      label,
      route,
    })),
  );
}
