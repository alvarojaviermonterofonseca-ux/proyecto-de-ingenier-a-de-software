import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

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
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly sidebarOpen = signal(false);
  protected readonly pageTitle = signal('Inicio');
  protected readonly today = new Intl.DateTimeFormat('es-CO', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date());

  protected readonly groups = computed(() =>
    NAV_GROUPS.map((group) => ({
      ...group,
      items: group.items.filter((item) => this.canSee(item)),
    })).filter((group) => group.items.length > 0),
  );

  protected readonly role = computed(() => roleLabel(this.auth.roleName()));

  constructor() {
    this.updateTitle();
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.updateTitle();
        this.sidebarOpen.set(false);
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

  private canSee(item: NavItem): boolean {
    if (item.adminOnly && !this.auth.isAdmin()) {
      return false;
    }
    if (!item.permission) {
      return true;
    }
    return this.auth.hasAny(
      Array.isArray(item.permission) ? item.permission : [item.permission],
    );
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
