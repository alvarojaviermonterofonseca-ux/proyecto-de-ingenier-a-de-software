export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiErrorPayload {
  error: {
    codigo: number;
    mensaje: string;
    detalles: unknown;
  };
}

export interface Permission {
  id: number;
  codigo: string;
  recurso: string;
  accion: string;
  descripcion: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Role {
  id: number;
  nombre: string;
  descripcion: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  permisos: string[];
  permisos_detalle: Permission[];
  total_usuarios: number;
}

export interface RoleOption {
  id: number;
  nombre: string;
}

export interface ProfileSummary {
  usuario?: number;
  nombre?: string;
  correo?: string;
  objetivo?: string;
  especialidad?: string;
  turno_preferido?: string;
  cargo?: string;
}

export interface UserSummary {
  id: number;
  rol: number;
  rol_nombre: string;
  roles_efectivos: RoleOption[];
  nombre: string;
  username: string | null;
  correo: string;
  telefono: string | null;
  is_active: boolean;
  perfil_detalle: ProfileSummary | null;
}

export interface UserDetail {
  id: number;
  rol: number;
  rol_detalle: Role;
  roles_detalle: Role[];
  permisos: string[];
  nombre: string;
  username: string | null;
  correo: string;
  telefono: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  perfil_detalle: ProfileSummary | null;
}

export interface CurrentUser extends UserDetail {
  roles_efectivos: Role[];
  permisos_efectivos: string[];
}

export interface LoginResponse {
  mensaje: string;
  token: string;
  tipo_token: string;
  expira_at: string;
  usuario: UserDetail;
}

export interface UserPayload {
  rol: number;
  nombre: string;
  username?: string | null;
  correo: string;
  contrasena?: string;
  telefono?: string | null;
  is_active?: boolean;
  roles_asignados?: number[];
  perfil?: Record<string, unknown>;
}

export interface ClientProfile {
  usuario: number;
  usuario_detalle: UserSummary;
  tipo_documento: string | null;
  numero_documento: string | null;
  fecha_nacimiento: string | null;
  objetivo: string | null;
  peso_kg: string | null;
  estatura_cm: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OperationalClientProfile {
  usuario: number;
  usuario_detalle: UserSummary;
  tipo_documento: string | null;
  numero_documento: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrainerProfile {
  usuario: number;
  usuario_detalle: UserSummary;
  especialidad: string | null;
  certificacion: string | null;
  fecha_ingreso: string | null;
  biografia: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TherapistProfile {
  usuario: number;
  usuario_detalle: UserSummary;
  especialidad: string | null;
  licencia_profesional: string | null;
  fecha_ingreso: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReceptionistProfile {
  usuario: number;
  usuario_detalle: UserSummary;
  fecha_ingreso: string | null;
  turno_preferido: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdministratorProfile {
  usuario: number;
  usuario_detalle: UserSummary;
  cargo: string | null;
  fecha_ingreso: string | null;
  nivel_permisos: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClientTrainerAssignment {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  entrenador: number;
  entrenador_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  };
  fecha_inicio: string;
  fecha_fin: string | null;
  activo: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClientTherapistAssignment {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  terapeuta: number;
  terapeuta_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  };
  fecha_inicio: string;
  fecha_fin: string | null;
  activo: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Attendance {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  entrada_at: string;
  salida_at: string | null;
  metodo_entrada: string;
  identificador_evento: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Workout {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  entrenador: number | null;
  entrenador_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  } | null;
  inicio_at: string;
  fin_at: string | null;
  duracion_minutos: number | null;
  observaciones: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Exercise {
  id: number;
  nombre: string;
  descripcion: string | null;
  grupo_muscular: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrainingPlan {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  entrenador: number;
  entrenador_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  };
  nombre: string;
  objetivo: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  activo: boolean;
  observaciones: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrainingPlanExercise {
  id: number;
  plan: number;
  ejercicio: number;
  ejercicio_detalle: Exercise;
  orden: number;
  series: number | null;
  repeticiones: number | null;
  peso_kg: string | null;
  descanso_segundos: number | null;
  observaciones: string | null;
  created_at: string;
  updated_at: string;
}

export interface NutritionPlan {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  responsable: number;
  responsable_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  };
  nombre: string;
  objetivo: string;
  calorias_objetivo: string | null;
  fecha_inicio: string;
  fecha_fin: string | null;
  activo: boolean;
  observaciones: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Meal {
  id: number;
  plan_alimentacion: number;
  nombre: string;
  tipo: string;
  hora_sugerida: string | null;
  descripcion: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FoodRecord {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  comida: number | null;
  comida_nombre: string | null;
  registrado_at: string;
  foto_url: string | null;
  verificado: boolean;
  calificacion: string | null;
  observaciones: string | null;
  revisado_por: number | null;
  revisado_por_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  } | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: number;
  usuario: number;
  usuario_detalle: UserSummary;
  tipo: string;
  titulo: string;
  mensaje: string;
  programada_at: string | null;
  enviada_at: string | null;
  estado: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserRoleAssignment {
  id: number;
  usuario: number;
  rol: number;
  usuario_nombre: string;
  rol_nombre: string;
  activo: boolean;
  asignado_por: number | null;
  asignado_por_nombre: string | null;
  created_at: string;
  updated_at: string;
}

export interface RolePermissionAssignment {
  id: number;
  rol: number;
  rol_nombre: string;
  permiso: number;
  permiso_codigo: string;
  created_at: string;
}

export interface AuditEvent {
  id: number;
  actor: number | null;
  actor_nombre: string | null;
  accion: string;
  recurso: string;
  objeto_id: string | null;
  detalles: Record<string, unknown>;
  created_at: string;
}

export interface WeeklyVisitDay {
  fecha: string;
  etiqueta: string;
  total: number;
}

export interface OpenAttendance {
  id: number;
  entrada_at: string;
}

export interface SummaryMetrics {
  usuarios_activos: number;
  clientes_activos: number;
  entrenadores_activos: number;
  terapeutas_activos: number;
  asistencias_hoy: number;
  asistencias_abiertas: number;
  entrenamientos_hoy: number;
  planes_entrenamiento_activos: number;
  planes_alimentacion_activos: number;
  registros_comida_pendientes: number;
  notificaciones_pendientes: number;
  visitas_semana: number;
  visitas_semana_dias: WeeklyVisitDay[];
}

export interface Summary {
  rol_principal: string;
  es_cliente: boolean;
  metricas: SummaryMetrics;
  asistencia_abierta: OpenAttendance | null;
  asistencias_recientes: Attendance[];
  notificaciones_recientes: Notification[];
  actividad_reciente: AuditEvent[];
}

/** Total de registros por recurso (`GET /api/v1/conteos/`). */
export type ResourceCounts = Record<string, number>;
