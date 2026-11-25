import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { ModuleTabsComponent, type ModuleTab } from '../../shared/module-tabs.component';

const TABS: readonly (ModuleTab & { permission?: string; adminOnly?: boolean })[] = [
  { label: 'Ingresos', route: '/financiero/ingresos', permission: 'pagos:view' },
  { label: 'Gastos', route: '/financiero/gastos', permission: 'gastos:view' },
  { label: 'Membresías', route: '/financiero/membresias', permission: 'membresias:view' },
  { label: 'Alertas', route: '/financiero/alertas', permission: 'alertas:view' },
  { label: 'Reportes', route: '/financiero/reportes', permission: 'pagos:export' },
  { label: 'Configuración', route: '/financiero/configuracion', adminOnly: true },
];

/**
 * Secciones del módulo financiero como pestañas sobre el contenido, igual que
 * el módulo de autorizados. Antes era un segundo menú lateral que en pantallas
 * de menos de 1024 px quedaba fijo encima de la página y no se podía cerrar.
 */
@Component({
  selector: 'app-financial-layout',
  standalone: true,
  imports: [RouterOutlet, ModuleTabsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <app-module-tabs [tabs]="tabs()" />
    <router-outlet />
  `,
})
export class FinancialLayout {
  private readonly auth = inject(AuthService);

  protected readonly tabs = computed<ModuleTab[]>(() =>
    TABS.filter(
      (tab) =>
        (!tab.permission || this.auth.hasPermission(tab.permission)) &&
        (!tab.adminOnly || this.auth.isAdmin()),
    ).map(({ label, route }) => ({
      label,
      route,
    })),
  );
}
