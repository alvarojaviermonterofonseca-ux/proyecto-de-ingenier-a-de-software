import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth/auth.guard';
import { permissionGuard } from './core/rbac/permission.guard';

export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login.page').then((m) => m.LoginPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'inicio' },
      {
        path: 'inicio',
        data: { title: 'Inicio' },
        loadComponent: () =>
          import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage),
      },
      {
        path: 'usuarios',
        pathMatch: 'full',
        redirectTo: 'autorizados/usuarios',
      },
      {
        path: 'roles',
        pathMatch: 'full',
        redirectTo: 'autorizados/seguridad/roles',
      },
      {
        path: 'autorizados',
        canActivate: [permissionGuard],
        data: {
          title: 'Autorizados',
          permission: ['usuarios:view', 'roles:view', 'permisos:view'],
        },
        loadComponent: () =>
          import('./features/authorized/authorized.layout').then((m) => m.AuthorizedLayout),
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'usuarios' },
          {
            path: 'usuarios',
            data: { title: 'Usuarios', permission: 'usuarios:view' },
            loadComponent: () =>
              import('./features/authorized/users/authorized-users.page').then(
                (m) => m.AuthorizedUsersPage,
              ),
          },
          {
            path: 'seguridad/roles',
            data: {
              title: 'Roles y permisos',
              permission: 'roles:view',
            },
            loadComponent: () =>
              import('./features/authorized/security/security-roles.page').then(
                (m) => m.SecurityRolesPage,
              ),
          },
          {
            path: 'seguridad/permisos',
            data: {
              title: 'Catálogo de permisos',
              permission: 'permisos:view',
            },
            loadComponent: () =>
              import('./features/authorized/security/security-permissions.page').then(
                (m) => m.SecurityPermissionsPage,
              ),
          },
          {
            path: 'seguridad/asignaciones',
            data: {
              title: 'Asignaciones de rol',
              permission: 'usuarios:view',
            },
            loadComponent: () =>
              import('./features/authorized/security/security-assignments.page').then(
                (m) => m.SecurityAssignmentsPage,
              ),
          },
        ],
      },
      {
        path: 'mi-acceso',
        data: { title: 'Mi acceso' },
        loadComponent: () =>
          import('./features/access/my-access.page').then((m) => m.MyAccessPage),
      },
      {
        path: 'andromeda',
        data: { title: 'Andrómeda' },
        loadComponent: () =>
          import('./features/downloads/andromeda.page').then((m) => m.AndromedaPage),
      },
      {
        path: 'auditoria',
        canActivate: [permissionGuard],
        data: { title: 'Auditoría', permission: 'usuarios:view', adminOnly: true },
        loadComponent: () => import('./features/audit/audit.page').then((m) => m.AuditPage),
      },
      {
        path: 'clientes',
        canActivate: [permissionGuard],
        data: { title: 'Clientes', permission: 'clientes:view' },
        loadComponent: () => import('./features/clients/clients.page').then((m) => m.ClientsPage),
      },
      {
        path: 'equipo',
        canActivate: [permissionGuard],
        data: {
          title: 'Equipo',
          permission: [
            'entrenadores:view',
            'terapeutas:view',
            'recepcionistas:view',
            'administradores:view',
          ],
        },
        loadComponent: () => import('./features/team/team.page').then((m) => m.TeamPage),
      },
      {
        path: 'asignaciones',
        canActivate: [permissionGuard],
        data: {
          title: 'Asignaciones',
          permission: ['asignaciones-cliente-entrenador:view', 'clientes-terapeutas:view'],
        },
        loadComponent: () =>
          import('./features/assignments/assignments.page').then((m) => m.AssignmentsPage),
      },
      {
        path: 'asistencias',
        canActivate: [permissionGuard],
        data: { title: 'Asistencias', permission: 'asistencias:view' },
        loadComponent: () =>
          import('./features/attendance/attendance.page').then((m) => m.AttendancePage),
      },
      {
        path: 'entrenamientos',
        canActivate: [permissionGuard],
        data: { title: 'Entrenamientos', permission: 'entrenamientos:view' },
        loadComponent: () =>
          import('./features/workouts/workouts.page').then((m) => m.WorkoutsPage),
      },
      {
        path: 'ejercicios',
        canActivate: [permissionGuard],
        data: { title: 'Ejercicios', permission: 'ejercicios:view' },
        loadComponent: () =>
          import('./features/exercises/exercises.page').then((m) => m.ExercisesPage),
      },
      {
        path: 'planes-entrenamiento',
        canActivate: [permissionGuard],
        data: { title: 'Planes de entrenamiento', permission: 'planes-entrenamiento:view' },
        loadComponent: () =>
          import('./features/training-plans/training-plans.page').then((m) => m.TrainingPlansPage),
      },
      {
        path: 'planes-alimentacion',
        canActivate: [permissionGuard],
        data: { title: 'Planes de alimentación', permission: 'planes-alimentacion:view' },
        loadComponent: () =>
          import('./features/nutrition-plans/nutrition-plans.page').then((m) => m.NutritionPlansPage),
      },
      {
        path: 'comidas',
        canActivate: [permissionGuard],
        data: { title: 'Comidas', permission: 'comidas:view' },
        loadComponent: () => import('./features/meals/meals.page').then((m) => m.MealsPage),
      },
      {
        path: 'registros-comida',
        canActivate: [permissionGuard],
        data: { title: 'Registros de comida', permission: 'registros-comida:view' },
        loadComponent: () =>
          import('./features/food-records/food-records.page').then((m) => m.FoodRecordsPage),
      },
      {
        path: 'notificaciones',
        canActivate: [permissionGuard],
        data: { title: 'Notificaciones', permission: 'notificaciones:view' },
        loadComponent: () =>
          import('./features/notifications/notifications.page').then((m) => m.NotificationsPage),
      },
      {
        path: 'perfil',
        data: { title: 'Mi perfil' },
        loadComponent: () => import('./features/profile/profile.page').then((m) => m.ProfilePage),
      },
      {
        path: 'acceso-denegado',
        data: { title: 'Acceso restringido' },
        loadComponent: () =>
          import('./features/errors/forbidden.page').then((m) => m.ForbiddenPage),
      },
    ],
  },
  {
    path: '**',
    loadComponent: () =>
      import('./features/errors/not-found.page').then((m) => m.NotFoundPage),
  },
];
