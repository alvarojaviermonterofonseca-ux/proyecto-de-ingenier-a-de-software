export interface NavItem {
  label: string;
  route: string;
  icon: string;
  permission?: string | string[];
  permissionMode?: 'any' | 'all';
  adminOnly?: boolean;
  exact?: boolean;
  /**
   * Recursos cuyo total se muestra como distintivo. Con varios recursos
   * (por ejemplo Equipo) el distintivo suma sus conteos.
   */
  counts?: readonly string[];
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: 'General',
    items: [{ label: 'Inicio', route: '/inicio', icon: 'home', exact: true }],
  },
  {
    label: 'Autorizados',
    items: [
      {
        label: 'Usuarios',
        route: '/autorizados/usuarios',
        icon: 'users',
        permission: 'usuarios:view',
        counts: ['usuarios'],
      },
      {
        label: 'Roles y permisos',
        route: '/autorizados/seguridad/roles',
        icon: 'shield',
        permission: 'roles:view',
        counts: ['roles'],
      },
      {
        label: 'Catálogo de permisos',
        route: '/autorizados/seguridad/permisos',
        icon: 'lock',
        permission: 'permisos:view',
        counts: ['permisos'],
      },
      {
        label: 'Asignaciones de rol',
        route: '/autorizados/seguridad/asignaciones',
        icon: 'target',
        permission: 'usuarios:view',
        counts: ['usuarios-roles'],
      },
      {
        label: 'Auditoría',
        route: '/auditoria',
        icon: 'audit',
        adminOnly: true,
        counts: ['auditoria'],
      },
    ],
  },
  {
    label: 'Catálogo',
    items: [
      {
        label: 'Ejercicios',
        route: '/ejercicios',
        icon: 'dumbbell',
        permission: 'ejercicios:view',
        counts: ['ejercicios'],
      },
      {
        label: 'Planes de entrenamiento',
        route: '/planes-entrenamiento',
        icon: 'clipboard',
        permission: 'planes-entrenamiento:view',
        counts: ['planes-entrenamiento'],
      },
      {
        label: 'Planes de alimentación',
        route: '/planes-alimentacion',
        icon: 'salad',
        permission: 'planes-alimentacion:view',
        counts: ['planes-alimentacion'],
      },
      {
        label: 'Comidas',
        route: '/comidas',
        icon: 'apple',
        permission: 'comidas:view',
        counts: ['comidas'],
      },
    ],
  },
  {
    label: 'Gestión',
    items: [
      {
        label: 'Clientes',
        route: '/clientes',
        icon: 'user',
        permission: 'clientes:view',
        counts: ['clientes'],
      },
      {
        label: 'Equipo',
        route: '/equipo',
        icon: 'users',
        permission: [
          'entrenadores:view',
          'terapeutas:view',
          'recepcionistas:view',
          'administradores:view',
        ],
        counts: ['entrenadores', 'terapeutas', 'recepcionistas', 'administradores'],
      },
      {
        label: 'Asignaciones de clientes',
        route: '/asignaciones',
        icon: 'target',
        permission: ['asignaciones-cliente-entrenador:view', 'clientes-terapeutas:view'],
        counts: ['asignaciones-cliente-entrenador', 'clientes-terapeutas'],
      },
      {
        label: 'Asistencias',
        route: '/asistencias',
        icon: 'clock',
        permission: 'asistencias:view',
        counts: ['asistencias'],
      },
      {
        label: 'Entrenamientos',
        route: '/entrenamientos',
        icon: 'calendar',
        permission: 'entrenamientos:view',
        counts: ['entrenamientos'],
      },
      {
        label: 'Registros de comida',
        route: '/registros-comida',
        icon: 'camera',
        permission: 'registros-comida:view',
        counts: ['registros-comida'],
      },
      {
        label: 'Notificaciones',
        route: '/notificaciones',
        icon: 'bell',
        permission: 'notificaciones:view',
        counts: ['notificaciones'],
      },
    ],
  },
  {
    label: 'Cuenta',
    items: [
      { label: 'Mi perfil', route: '/perfil', icon: 'settings' },
      { label: 'Mi acceso', route: '/mi-acceso', icon: 'lock' },
      { label: 'Andrómeda', route: '/andromeda', icon: 'smartphone' },
    ],
  },
];
