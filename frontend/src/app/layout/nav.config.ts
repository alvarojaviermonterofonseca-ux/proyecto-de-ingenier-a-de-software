export interface NavItem {
  label: string;
  route: string;
  icon: string;
  permission?: string | string[];
  adminOnly?: boolean;
  exact?: boolean;
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
    label: 'Gestión',
    items: [
      { label: 'Usuarios', route: '/usuarios', icon: 'users', permission: 'usuarios:view' },
      { label: 'Roles y permisos', route: '/roles', icon: 'shield', permission: 'roles:view' },
      { label: 'Auditoría', route: '/auditoria', icon: 'audit', adminOnly: true },
    ],
  },
  {
    label: 'Personas',
    items: [
      { label: 'Clientes', route: '/clientes', icon: 'user', permission: 'clientes:view' },
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
      },
      {
        label: 'Asignaciones',
        route: '/asignaciones',
        icon: 'target',
        permission: ['asignaciones-cliente-entrenador:view', 'clientes-terapeutas:view'],
      },
    ],
  },
  {
    label: 'Operación',
    items: [
      { label: 'Asistencias', route: '/asistencias', icon: 'clock', permission: 'asistencias:view' },
      {
        label: 'Entrenamientos',
        route: '/entrenamientos',
        icon: 'calendar',
        permission: 'entrenamientos:view',
      },
      { label: 'Ejercicios', route: '/ejercicios', icon: 'dumbbell', permission: 'ejercicios:view' },
      {
        label: 'Planes de entrenamiento',
        route: '/planes-entrenamiento',
        icon: 'clipboard',
        permission: 'planes-entrenamiento:view',
      },
    ],
  },
  {
    label: 'Nutrición',
    items: [
      {
        label: 'Planes de alimentación',
        route: '/planes-alimentacion',
        icon: 'salad',
        permission: 'planes-alimentacion:view',
      },
      { label: 'Comidas', route: '/comidas', icon: 'apple', permission: 'comidas:view' },
      {
        label: 'Registros de comida',
        route: '/registros-comida',
        icon: 'camera',
        permission: 'registros-comida:view',
      },
    ],
  },
  {
    label: 'Comunicación',
    items: [
      {
        label: 'Notificaciones',
        route: '/notificaciones',
        icon: 'bell',
        permission: 'notificaciones:view',
      },
    ],
  },
  {
    label: 'Cuenta',
    items: [{ label: 'Mi perfil', route: '/perfil', icon: 'settings' }],
  },
];
