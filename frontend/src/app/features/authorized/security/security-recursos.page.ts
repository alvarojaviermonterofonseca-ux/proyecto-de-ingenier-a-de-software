import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ApiClient } from '../../../core/api/api-client.service';
import { ApiError } from '../../../core/api/api-error';
import type { Permission, ResourceAlias } from '../../../core/api/api.models';
import { AuthService } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../core/ui/confirm.service';
import { ToastService } from '../../../core/ui/toast.service';
import { EmptyStateComponent } from '../../../shared/empty-state.component';
import { IconComponent } from '../../../shared/icon.component';
import { PageHeaderComponent } from '../../../shared/page-header.component';

const ALIAS_MAX = 60;

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
  protected readonly auth = inject(AuthService);

  protected readonly canEdit = computed(() =>
    this.auth.isAdmin() || this.auth.hasPermission('permisos:edit'),
  );

  protected readonly recursos = signal<RecursoAlias[]>([]);
  /** Alias tal como están guardados en el servidor (recurso -> nombre). */
  protected readonly guardados = signal<Record<string, string>>({});
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly query = signal('');
  protected readonly aliasMax = ALIAS_MAX;

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
        // Los alias se aplican cuando ya existe la lista de recursos.
        this.cargarAliasGuardados();
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

  /** Lee los alias del servidor: son comunes a todos los usuarios. */
  private cargarAliasGuardados(): void {
    this.api.get<ResourceAlias[]>('resource-aliases/').subscribe({
      next: (filas) => {
        const guardados: Record<string, string> = {};
        for (const fila of filas) {
          if (fila.tiene_alias) guardados[fila.nombre_original] = fila.nombre_actual;
        }
        this.guardados.set(guardados);
        this.recursos.update((lista) =>
          lista.map((r) => ({ ...r, alias: guardados[r.recurso] ?? '' })),
        );
      },
      error: (error: unknown) => {
        this.toast.error(
          'No se pudieron cargar los nombres guardados',
          error instanceof ApiError ? error.message : undefined,
        );
      },
    });
  }

  protected updateQuery(value: string): void {
    this.query.set(value);
  }

  protected guardarAliasRecurso(recurso: string): void {
    this.formError.set(null);
    const fila = this.recursos().find((r) => r.recurso === recurso);
    if (!fila || this.saving()) return;
    const nuevoAlias = fila.alias.trim();
    if (nuevoAlias.length > ALIAS_MAX) {
      this.formError.set(`El nombre no puede superar ${ALIAS_MAX} caracteres.`);
      return;
    }
    // El blur también llama aquí: no se envía nada si no cambió.
    if (nuevoAlias === (this.guardados()[recurso] ?? '')) return;
    this.enviarAlias(recurso, nuevoAlias, nuevoAlias ? 'Alias guardado' : 'Alias eliminado');
  }

  protected cancelarEdicion(recurso: string): void {
    this.restaurar(recurso);
    this.formError.set(null);
  }

  /** Guarda el alias en el servidor; un texto vacío lo elimina. */
  private enviarAlias(recurso: string, alias: string, titulo: string): void {
    this.saving.set(true);
    this.api
      .put<ResourceAlias>(`resource-aliases/${encodeURIComponent(recurso)}/`, {
        nombre_actual: alias,
      })
      .subscribe({
        next: (respuesta) => {
          this.saving.set(false);
          const valor = respuesta.tiene_alias ? respuesta.nombre_actual : '';
          this.guardados.update((actuales) => {
            const copia = { ...actuales };
            if (valor) copia[recurso] = valor;
            else delete copia[recurso];
            return copia;
          });
          this.recursos.update((lista) =>
            lista.map((r) => (r.recurso === recurso ? { ...r, alias: valor } : r)),
          );
          this.toast.success(titulo, `Nombre de visualización actualizado para ${recurso}.`);
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.restaurar(recurso);
          this.toast.error(
            'No se pudo guardar el nombre',
            error instanceof ApiError ? error.message : undefined,
          );
        },
      });
  }

  /** Devuelve la fila al valor guardado en el servidor. */
  private restaurar(recurso: string): void {
    const valor = this.guardados()[recurso] ?? '';
    this.recursos.update((lista) =>
      lista.map((r) => (r.recurso === recurso ? { ...r, alias: valor } : r)),
    );
  }

  protected async eliminarAlias(recurso: string): Promise<void> {
    const accepted = await this.confirm.confirm({
      title: 'Eliminar alias',
      message: `Se borrará el nombre personalizado de "${recurso}" y se mostrará su nombre original.`,
      confirmLabel: 'Eliminar alias',
      tone: 'danger',
    });
    if (!accepted) return;
    this.enviarAlias(recurso, '', 'Alias eliminado');
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
