/**
 * RBAC del panel: los permisos llegan desde la API y se evalúan en memoria.
 * La base de datos es la fuente de verdad; este módulo solo refleja lo que el
 * servidor autorizó para el usuario autenticado.
 *
 * @typedef {"view" | "create" | "edit" | "delete" | "export"} PermissionAction
 * @typedef {
 *   "roles" | "permisos" | "usuarios" | "clientes" | "entrenadores" | "terapeutas" |
 *   "recepcionistas" | "administradores" | "asignaciones-cliente-entrenador" |
 *   "clientes-terapeutas" | "asistencias" | "entrenamientos" | "ejercicios" | "planes-entrenamiento" |
 *   "planes-entrenamiento-ejercicios" | "planes-alimentacion" | "comidas" |
 *   "registros-comida" | "notificaciones"
 * } Resource
 * @typedef {{ id: number, nombre: string, descripcion?: string, is_active?: boolean, permisos?: string[] }} Role
 * @typedef {{ id: number, rol_detalle?: Role, rol_nombre?: string, roles_efectivos?: Role[], roles_detalle?: Role[], permisos_efectivos?: string[], permisos?: string[], nombre: string }} AuthenticatedUser
 */

export const ACTIONS = Object.freeze(["view", "create", "edit", "delete", "export"]);

export const RESOURCES = Object.freeze({
  roles: "roles",
  permissions: "permisos",
  users: "usuarios",
  clients: "clientes",
  coaches: "entrenadores",
  therapists: "terapeutas",
  receptionists: "recepcionistas",
  administrators: "administradores",
  assignments: "asignaciones-cliente-entrenador",
  clientTherapists: "clientes-terapeutas",
  attendance: "asistencias",
  workouts: "entrenamientos",
  exercises: "ejercicios",
  workoutPlans: "planes-entrenamiento",
  workoutPlanExercises: "planes-entrenamiento-ejercicios",
  nutritionPlans: "planes-alimentacion",
  meals: "comidas",
  mealLogs: "registros-comida",
  notifications: "notificaciones",
});

const VALID_RESOURCES = new Set(Object.values(RESOURCES));
const VALID_ACTIONS = new Set(ACTIONS);

function roleNamesFor(user) {
  const assigned = (user?.roles_efectivos || user?.roles_detalle || [])
    .map((role) => (typeof role === "string" ? role : role?.nombre))
    .filter(Boolean);
  const primaryRole = user?.rol_detalle?.nombre || user?.rol_nombre;
  return [...new Set([primaryRole, ...assigned].filter(Boolean))];
}

function policyFromRoles(roles) {
  const policy = {};
  for (const role of roles.filter((entry) => entry.is_active !== false)) {
    const grants = {};
    for (const codigo of role.permisos || []) {
      const separator = codigo.indexOf(":");
      if (separator < 0) {
        continue;
      }
      const resource = codigo.slice(0, separator);
      const action = codigo.slice(separator + 1);
      if (VALID_RESOURCES.has(resource) && VALID_ACTIONS.has(action)) {
        (grants[resource] ||= []).push(action);
      }
    }
    policy[role.nombre] = grants;
  }
  return policy;
}

/**
 * Creates a deny-by-default checker backed by the permissions returned by the API.
 * @param {Role[]} roles
 */
export function createAccessControl(roles = []) {
  const roleList = roles.filter((role) => role.is_active !== false);
  const policy = policyFromRoles(roleList);

  function permissionCodesFor(user) {
    const codigos = Array.isArray(user?.permisos_efectivos)
      ? user.permisos_efectivos
      : user?.permisos;
    if (Array.isArray(codigos)) {
      return new Set(codigos);
    }
    const codes = new Set();
    for (const roleName of roleNamesFor(user)) {
      for (const [resource, actions] of Object.entries(policy[roleName] || {})) {
        for (const action of actions) {
          codes.add(`${resource}:${action}`);
        }
      }
    }
    return codes;
  }

  /**
   * @param {AuthenticatedUser} user
   * @param {Resource} resource
   * @param {PermissionAction} action
   */
  function can(user, resource, action) {
    if (!VALID_RESOURCES.has(resource) || !VALID_ACTIONS.has(action)) {
      return false;
    }
    if (!user || user.is_active === false) {
      return false;
    }
    return permissionCodesFor(user).has(`${resource}:${action}`);
  }

  function assignedRoles(user) {
    return roleNamesFor(user);
  }

  function permissionsFor(roleName) {
    return policy[roleName] || {};
  }

  return {
    can,
    assignedRoles,
    permissionsFor,
    warnings: [],
  };
}
