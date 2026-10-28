import type { Permission } from '../api/api.models';

export const RESOURCES = [
  'roles',
  'permisos',
  'usuarios',
  'clientes',
  'entrenadores',
  'terapeutas',
  'recepcionistas',
  'administradores',
  'asignaciones-cliente-entrenador',
  'clientes-terapeutas',
  'asistencias',
  'entrenamientos',
  'ejercicios',
  'planes-entrenamiento',
  'planes-entrenamiento-ejercicios',
  'planes-alimentacion',
  'comidas',
  'registros-comida',
  'notificaciones',
] as const;

export const ACTIONS = ['view', 'create', 'edit', 'delete', 'export'] as const;

export type Resource = (typeof RESOURCES)[number];
export type Action = (typeof ACTIONS)[number];
export type PermissionCode = `${Resource}:${Action}` | string;

export interface ResourceDefinition {
  code: Resource;
  label: string;
  description: string;
}

export const RESOURCE_DEFINITIONS: readonly ResourceDefinition[] = [
  { code: 'roles', label: 'Roles', description: 'Definición de roles y sus permisos.' },
  { code: 'permisos', label: 'Permisos', description: 'Catálogo global de permisos.' },
  { code: 'usuarios', label: 'Usuarios', description: 'Cuentas, identidad y asignación de roles.' },
  { code: 'clientes', label: 'Clientes', description: 'Perfiles y datos de clientes.' },
  { code: 'entrenadores', label: 'Entrenadores', description: 'Perfiles del equipo de entrenamiento.' },
  { code: 'terapeutas', label: 'Terapeutas', description: 'Perfiles del equipo terapéutico.' },
  { code: 'recepcionistas', label: 'Recepcionistas', description: 'Perfiles de recepción.' },
  { code: 'administradores', label: 'Administradores', description: 'Perfiles administrativos.' },
  {
    code: 'asignaciones-cliente-entrenador',
    label: 'Asignaciones cliente-entrenador',
    description: 'Vínculos entre clientes y entrenadores.',
  },
  {
    code: 'clientes-terapeutas',
    label: 'Asignaciones cliente-terapeuta',
    description: 'Vínculos entre clientes y terapeutas.',
  },
  { code: 'asistencias', label: 'Asistencias', description: 'Entradas y salidas al gimnasio.' },
  { code: 'entrenamientos', label: 'Entrenamientos', description: 'Sesiones de entrenamiento.' },
  { code: 'ejercicios', label: 'Ejercicios', description: 'Catálogo de ejercicios.' },
  {
    code: 'planes-entrenamiento',
    label: 'Planes de entrenamiento',
    description: 'Planes asignados a clientes.',
  },
  {
    code: 'planes-entrenamiento-ejercicios',
    label: 'Ejercicios de planes',
    description: 'Filas de ejercicio dentro de un plan.',
  },
  {
    code: 'planes-alimentacion',
    label: 'Planes de alimentación',
    description: 'Planes nutricionales por cliente.',
  },
  { code: 'comidas', label: 'Comidas', description: 'Comidas definidas en cada plan.' },
  { code: 'registros-comida', label: 'Registros de comida', description: 'Evidencias y revisión de comidas.' },
  { code: 'notificaciones', label: 'Notificaciones', description: 'Mensajes y recordatorios.' },
];

export const ACTION_LABELS: Record<Action, string> = {
  view: 'Ver',
  create: 'Crear',
  edit: 'Editar',
  delete: 'Eliminar',
  export: 'Exportar',
};

export const ROLE_LABELS: Record<string, string> = {
  administrador: 'Administrador',
  recepcionista: 'Recepcionista',
  entrenador: 'Entrenador',
  terapeuta: 'Terapeuta',
  cliente: 'Cliente',
};

export function permissionCode(resource: Resource, action: Action): PermissionCode {
  return `${resource}:${action}`;
}

export function resourceLabel(resource: string): string {
  return RESOURCE_DEFINITIONS.find((item) => item.code === resource)?.label ?? humanize(resource);
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action as Action] ?? humanize(action);
}

export function roleLabel(role: string | null | undefined): string {
  if (!role) {
    return 'Sin rol';
  }
  return ROLE_LABELS[role] ?? humanize(role);
}

export function humanize(value: string): string {
  const normalized = value.replaceAll('-', ' ').replaceAll('_', ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export interface PermissionGroup {
  resource: ResourceDefinition;
  permissions: Permission[];
}

export function groupPermissions(permissions: readonly Permission[]): PermissionGroup[] {
  return RESOURCE_DEFINITIONS.map((resource) => ({
    resource,
    permissions: permissions
      .filter((permission) => permission.recurso === resource.code)
      .sort((a, b) => ACTIONS.indexOf(a.accion as Action) - ACTIONS.indexOf(b.accion as Action)),
  })).filter((group) => group.permissions.length > 0);
}
