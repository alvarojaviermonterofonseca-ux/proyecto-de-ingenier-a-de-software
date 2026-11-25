import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { ApiClient } from '../../../core/api/api-client.service';
import { ApiError } from '../../../core/api/api-error';
import type { Permission } from '../../../core/api/api.models';
import { AuthService } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';

const STORAGE_KEY = 'gym_recursos_alias';

interface RecursoAlias {
  recurso: string;
  alias: string;
}

/** Mapa de recurso (código de permiso) -> ruta de navegación del frontend. */
const RECURSO_RUTA: Record<string, string> = {
  usuarios: '/autorizados/usuarios',
  roles: '/autorizados/seguridad/roles',
  permisos: '/autorizados/seguridad/permisos',
  'usuarios-roles': '/autorizados/seguridad/asignaciones',
  clientes: '/clientes',
  entrenadores: '/equipo',
  terapeutas: '/equipo',
  recepcionistas: '/equipo',
  administradores: '/equipo',
  'asignaciones-cliente-entrenador': '/asignaciones',
  'clientes-terapeutas': '/asignaciones',
  asistencias: '/asistencias',
  entrenamientos: '/entrenamientos',
  ejercicios: '/ejercicios',
  'planes-entrenamiento': '/planes-entrenamiento',
  'planes-alimentacion': '/planes-alimentacion',
  comidas: '/comidas',
  'registros-comida': '/registros-comida',
  notificaciones: '/notificaciones',
  auditoria: '/auditoria',
};

@Component({
  selector: 'app-security-recursos',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    FormsModule,
    EmptyStateComponent,
    IconComponent,
    PageHeaderComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './security-recursos.page.html',
  styleUrl: './security-recursos.page.css',
})
export class SecurityRecursosPage {
  private readonly api = inject(ApiClient);
  private readonly router = inject(Router);
  private readonly confirm = inject(ConfirmService);
  private readonly toast = inject(ToastService);
  private readonly formBuilder = inject(FormBuilder);
  protected readonly auth = inject(AuthService);

  protected readonly canEdit = computed(() =>
    this.auth.isAdmin() || this.auth.hasPermission('permisos:edit'),
  );

  protected readonly recursos = signal<RecursoAlias[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly query = signal('');

  protected readonly form = this.formBuilder.nonNullable.group({
    alias: ['', [Validators.required, Validators.maxLength(60)]],
  });

  protected readonly visible = computed(() => {
    const q = this.query().trim().toLowerCase();
    return this.recursos().filter((r) => {
      if (!q) return true;
      return (
        r.recurso.toLowerCase().includes(q) ||
        r.alias.toLowerCase().includes(q)
      );
    });
  });

  ngOnInit(): void {
    this.load();
    this.cargarAliasGuardados();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getAll<Permission>('permisos/', { is_active: 1 }).subscribe({
      next: (permissions) => {
        // Extraer nombres de recurso únicos, manteniendo orden de primera aparición
        const vistos = new Set<string>();
        const lista: RecursoAlias[] = [];
        for (const p of permissions) {
          if (!vistos.has(p.recurso)) {
            vistos.add(p.recurso);
            lista.push({ recurso: p.recurso, alias: '' });
          }
        }
        this.recursos.set(lista);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(
          error instanceof ApiError
            ? error.message
            : 'No se pudo cargar el catálogo de recursos.',
        );
      },
    });
  }

  private cargarAliasGuardados(): void {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const guardados: Record<string, string> = JSON.parse(raw);
      this.recursos.update((lista) =>
        lista.map((r) => ({ ...r, alias: guardados[r.recurso] ?? r.alias })),
      );
    } catch {
      // Ignorar errores de parseo; se empieza con alias vacíos
    }
  }

  private guardarAlias(): void {
    const guardados: Record<string, string> = {};
    for (const r of this.recursos()) {
      if (r.alias.trim()) guardados[r.recurso] = r.alias.trim();
    }
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(guardados));
    } catch {
      // sessionStorage puede no estar disponible en algunos entornos
    }
  }

  protected updateQuery(value: string): void {
    this.query.set(value);
  }

  protected guardarAliasRecurso(recurso: string): void {
    this.formError.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const nuevoAlias = raw.alias.trim();

    this.recursos.update((lista) =>
      lista.map((r) =>
        r.recurso === recurso ? { ...r, alias: nuevoAlias } : r,
      ),
    );
    this.guardarAlias();
    this.toast.success('Alias guardado', `Nombre de visualización actualizado para ${recurso}.`);
  }

  protected cancelarEdicion(recurso: string): void {
    this.cargarAliasGuardados();
    this.formError.set(null);
  }

  protected async eliminarAlias(recurso: string): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar alias',
      message: `Se borrará el nombre personalizado de "${recurso}" y se mostrará su nombre original.`,
      confirmLabel: 'Eliminar alias',
      tone: 'danger',
    });
    if (!accepted) return;

    this.recursos.update((lista) =>
      lista.map((r) => (r.recurso === recurso ? { ...r, alias: '' } : r)),
    );
    this.guardarAlias();
    this.toast.success('Alias eliminado');
  }

  protected aliasPara(recurso: string): string {
    const r = this.recursos().find((x) => x.recurso === recurso);
    return r?.alias || '';
  }

  protected rutaPara(recurso: string): string {
    return RECURSO_RUTA[recurso] ?? `/${recurso}`;
  }

  protected navegarRecurso(recurso: string): void {
    const ruta = this.rutaPara(recurso);
    this.router.navigateByUrl(ruta);
  }

  protected esEditable(recurso: string): boolean {
    return !!this.rutaPara(recurso);
  }
}
