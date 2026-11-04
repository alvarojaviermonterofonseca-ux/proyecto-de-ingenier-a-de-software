import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, fromEvent } from 'rxjs';

import { ApiClient } from '../core/api/api-client.service';
import type { ResourceCounts } from '../core/api/api.models';
import { AuthService } from '../core/auth/auth.service';
import { LoadingService } from '../core/api/loading.service';
import { ConfirmService } from '../core/ui/confirm.service';
import { ThemeService } from '../core/ui/theme.service';
import { ToastService } from '../core/ui/toast.service';
import { roleLabel } from '../core/rbac/permissions';
import { AvatarComponent } from '../shared/avatar.component';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';
import { IconComponent } from '../shared/icon.component';
import { NAV_GROUPS, type NavItem } from './nav.config';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    IconComponent,
    AvatarComponent,
    ConfirmDialogComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.css',
})
export class ShellComponent {
  protected readonly auth = inject(AuthService);
  protected readonly theme = inject(ThemeService);
  protected readonly loading = inject(LoadingService);
  private readonly api = inject(ApiClient);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly sidebarOpen = signal(false);
  protected readonly pageTitle = signal('Inicio');
  protected readonly counts = signal<ResourceCounts>({});
  protected readonly today = capitalize(
    new Intl.DateTimeFormat('es-CO', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    }).format(new Date()),
  );

  protected readonly groups = computed(() => {
    const counts = this.counts();
    return NAV_GROUPS.map((group) => ({
      ...group,
      items: group.items
        .filter((item) => this.canSee(item))
        .map((item) => ({ ...item, count: contar(item, counts) })),
    })).filter((group) => group.items.length > 0);
  });

  protected readonly role = computed(() => roleLabel(this.auth.roleName()));

  constructor() {
    this.loadCounts();
    // Esperar al primer NavigationEnd para tener el snapshot completo del router
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.updateTitle();
        this.sidebarOpen.set(false);
        // Los totales se recalculan al navegar para reflejar altas y bajas.
        this.loadCounts();
      });

    // Título inicial: esperar microtask para que el router tenga el estado inicial
    Promise.resolve().then(() => this.updateTitle());

    // Al volver a la pestaña se refrescan permisos y conteos: si un
    // administrador cambió el rol, el menú se ajusta sin recargar la página.
    fromEvent(window, 'focus')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (!this.auth.authenticated()) return;
        this.auth.refresh().subscribe({ error: () => undefined });
        this.loadCounts();
      });
  }

  private loadCounts(): void {
    this.api
      .get<ResourceCounts>('conteos/')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (counts) => this.counts.set(counts ?? {}),
        // El menú sigue siendo utilizable aunque falle el conteo.
        error: () => this.counts.set({}),
      });
  }

  protected toggleSidebar(): void {
    this.sidebarOpen.update((open) => !open);
  }

  protected closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  protected async logout(): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Cerrar sesión',
      message: 'Se revocará la sesión actual en este navegador.',
      confirmLabel: 'Cerrar sesión',
      tone: 'danger',
    });
    if (!accepted) {
      return;
    }
    this.auth.logout().subscribe({
      next: () => void this.router.navigate(['/login']),
      error: () => {
        this.toast.error('No se pudo cerrar la sesión en el servidor', 'Se limpió la sesión local.');
        this.auth.clearSession();
        void this.router.navigate(['/login']);
      },
    });
  }

  protected async refreshPermissions(): Promise<void> {
    this.auth.refresh().subscribe({
      next: () => {
        this.toast.success('Permisos actualizados', 'Los cambios de rol ya están activos.');
        this.loadCounts();
      },
      error: () => this.toast.error('No se pudieron actualizar los permisos'),
    });
  }

  private canSee(item: NavItem): boolean {
    if (item.adminOnly && !this.auth.isAdmin()) {
      return false;
    }
    if (!item.permission) {
      return true;
    }
    const codes = Array.isArray(item.permission) ? item.permission : [item.permission];
    return item.permissionMode === 'all' ? this.auth.hasAll(codes) : this.auth.hasAny(codes);
  }

  private updateTitle(): void {
    let route = this.router.routerState.snapshot.root;
    let title = 'Gym Control Pro';
    while (route.firstChild) {
      route = route.firstChild;
      const routeTitle = route.data['title'];
      if (typeof routeTitle === 'string') {
        title = routeTitle;
      }
    }
    this.pageTitle.set(title);
  }
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/**
 * Total del distintivo de un elemento del menú. Con varios recursos suma sus
 * conteos; devuelve `null` cuando el elemento no muestra cifra o cuando el
 * backend no reportó ninguno de sus recursos.
 */
function contar(item: NavItem, counts: ResourceCounts): number | null {
  const claves = item.counts ?? [];
  if (claves.length === 0 || !claves.some((clave) => clave in counts)) {
    return null;
  }
  return claves.reduce((total, clave) => total + (counts[clave] ?? 0), 0);
}
