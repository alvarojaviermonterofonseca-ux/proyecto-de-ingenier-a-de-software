export interface NavItem {
  label: string;
  route: string;
  icon: string;
  permission?: string | string[];
  permissionMode?: 'any' | 'all';
  adminOnly?: boolean;
  exact?: boolean;
  /** Código del recurso del sistema (ej. 'clientes') para resolver su alias de nombre. */
  recurso?: string;
  /** Ruta original del recurso cuando se navega usando el alias. */
  rutaOriginal?: string;
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
    label: 'Dashboard',
    items: [
      {
        label: 'Dashboard Financiero',
        route: '/dashboard',
        icon: 'chart',
        permission: 'pagos:view',
        adminOnly: true,
      },
    ],
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
        recurso: 'usuarios',
        rutaOriginal: '/autorizados/usuarios',
      },
      {
        label: 'Roles y permisos',
        route: '/autorizados/seguridad/roles',
        icon: 'shield',
        permission: 'roles:view',
        counts: ['roles'],
        recurso: 'roles',
        rutaOriginal: '/autorizados/seguridad/roles',
      },
      {
        label: 'Catálogo de permisos',
        route: '/autorizados/seguridad/permisos',
        icon: 'lock',
        permission: 'permisos:view',
        counts: ['permisos'],
        recurso: 'permisos',
        rutaOriginal: '/autorizados/seguridad/permisos',
      },
      {
        label: 'Asignaciones de rol',
        route: '/autorizados/seguridad/asignaciones',
        icon: 'target',
        permission: 'usuarios:view',
        counts: ['usuarios-roles'],
        recurso: 'usuarios-roles',
        rutaOriginal: '/autorizados/seguridad/asignaciones',
      },
      {
        label: 'Auditoría',
        route: '/auditoria',
        icon: 'audit',
        adminOnly: true,
        counts: ['auditoria'],
        recurso: 'auditoria',
        rutaOriginal: '/auditoria',
      },
      {
        label: 'Nombres de recursos',
        route: '/autorizados/seguridad/recursos',
        icon: 'tag',
        permission: 'permisos:view',
        adminOnly: true,
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
        recurso: 'ejercicios',
        rutaOriginal: '/ejercicios',
      },
      {
        label: 'Planes de entrenamiento',
        route: '/planes-entrenamiento',
        icon: 'clipboard',
        permission: 'planes-entrenamiento:view',
        counts: ['planes-entrenamiento'],
        recurso: 'planes-entrenamiento',
        rutaOriginal: '/planes-entrenamiento',
      },
      {
        label: 'Planes de alimentación',
        route: '/planes-alimentacion',
        icon: 'salad',
        permission: 'planes-alimentacion:view',
        counts: ['planes-alimentacion'],
        recurso: 'planes-alimentacion',
        rutaOriginal: '/planes-alimentacion',
      },
      {
        label: 'Comidas',
        route: '/comidas',
        icon: 'apple',
        permission: 'comidas:view',
        counts: ['comidas'],
        recurso: 'comidas',
        rutaOriginal: '/comidas',
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
        recurso: 'clientes',
        rutaOriginal: '/clientes',
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
        recurso: 'asistencias',
        rutaOriginal: '/asistencias',
      },
      {
        label: 'Entrenamientos',
        route: '/entrenamientos',
        icon: 'calendar',
        permission: 'entrenamientos:view',
        counts: ['entrenamientos'],
        recurso: 'entrenamientos',
        rutaOriginal: '/entrenamientos',
      },
      {
        label: 'Registros de comida',
        route: '/registros-comida',
        icon: 'camera',
        permission: 'registros-comida:view',
        counts: ['registros-comida'],
        recurso: 'registros-comida',
        rutaOriginal: '/registros-comida',
      },
      {
        label: 'Notificaciones',
        route: '/notificaciones',
        icon: 'bell',
        permission: 'notificaciones:view',
        counts: ['notificaciones'],
        recurso: 'notificaciones',
        rutaOriginal: '/notificaciones',
      },
    ],
  },
  {
    label: 'Financiero',
    items: [
      {
        label: 'Ingresos',
        route: '/financiero/ingresos',
        icon: 'dollar-sign',
        permission: 'pagos:view',
        adminOnly: true,
        counts: ['pagos'],
        recurso: 'pagos',
        rutaOriginal: '/financiero/ingresos',
      },
      {
        label: 'Gastos',
        route: '/financiero/gastos',
        icon: 'credit-card',
        permission: 'gastos:view',
        adminOnly: true,
        counts: ['gastos'],
        recurso: 'gastos',
        rutaOriginal: '/financiero/gastos',
      },
      {
        label: 'Membresías',
        route: '/financiero/membresias',
        icon: 'id-card',
        permission: 'membresias:view',
        adminOnly: true,
        counts: ['membresias'],
        recurso: 'membresias',
        rutaOriginal: '/financiero/membresias',
      },
      {
        label: 'Alertas',
        route: '/financiero/alertas',
        icon: 'alert-triangle',
        permission: 'alertas:view',
        adminOnly: true,
        counts: ['alertas'],
        recurso: 'alertas',
        rutaOriginal: '/financiero/alertas',
      },
      {
        label: 'Reportes',
        route: '/financiero/reportes',
        icon: 'file-text',
        permission: 'pagos:export',
        adminOnly: true,
      },
      {
        label: 'Configuración',
        route: '/financiero/configuracion',
        icon: 'settings',
        adminOnly: true,
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
