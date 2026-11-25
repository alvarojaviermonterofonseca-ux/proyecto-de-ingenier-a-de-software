/** Interfaces TypeScript para los modelos financieros y administrativos */

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface MetodoPago {
  id: number;
  nombre: string;
  tipo: 'efectivo' | 'transferencia' | 'tarjeta' | 'otro';
  descripcion: string | null;
  is_active: boolean;
  requiere_referencia: boolean;
  orden: number;
  created_at: string;
  updated_at: string;
}

export interface CategoriaGasto {
  id: number;
  nombre: string;
  tipo: 'arriendo' | 'servicios_publicos' | 'nomina' | 'mantenimiento' | 'equipamiento' | 'limpieza' | 'publicidad' | 'internet' | 'otro';
  descripcion: string | null;
  is_active: boolean;
  color: string;
  orden: number;
  created_at: string;
  updated_at: string;
}

export interface Pago {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  concepto: 'membresia' | 'renovacion' | 'matricula' | 'entrenamiento_personal' | 'plan_alimentacion' | 'producto' | 'otro';
  concepto_detalle: string | null;
  membresia: number | null;
  membresia_detalle: {
    id: number;
    nombre: string;
    tipo: string;
    estado: string;
  } | null;
  fecha_pago: string;
  valor: string;
  metodo_pago: number;
  metodo_pago_detalle: MetodoPago;
  referencia: string | null;
  estado: 'completado' | 'pendiente' | 'fallido' | 'reembolsado';
  registrado_por: number;
  registrado_por_detalle: {
    id: number;
    nombre: string;
    correo: string;
  };
  notas: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface Gasto {
  id: number;
  descripcion: string;
  categoria: number;
  categoria_detalle: CategoriaGasto;
  valor: string;
  fecha: string;
  metodo_pago: number;
  metodo_pago_detalle: MetodoPago;
  referencia: string | null;
  estado: 'registrado' | 'aprobado' | 'pagado' | 'cancelado';
  registrado_por: number;
  registrado_por_detalle: {
    id: number;
    nombre: string;
    correo: string;
  };
  aprobado_por: number | null;
  aprobado_por_detalle: {
    id: number;
    nombre: string;
    correo: string;
  } | null;
  fecha_aprobacion: string | null;
  observaciones: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface Membresia {
  id: number;
  cliente: number;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  };
  tipo: 'mensual' | 'trimestral' | 'semestral' | 'anual' | 'visita' | 'personalizada';
  nombre: string;
  precio: string;
  fecha_inicio: string;
  fecha_fin: string;
  fecha_ultima_renovacion: string | null;
  estado: 'activa' | 'vencida' | 'por_vencer' | 'cancelada' | 'congelada';
  dias_congelados: number;
  renovacion_automatica: boolean;
  entrenador_asignado: number | null;
  entrenador_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
    especialidad: string | null;
  } | null;
  registrado_por: number;
  registrado_por_detalle: {
    id: number;
    nombre: string;
    correo: string;
  };
  observaciones: string | null;
  dias_para_vencer: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface Alerta {
  id: number;
  tipo: 'membresia_por_vencer' | 'membresia_vencida' | 'cliente_inactivo' | 'ingresos_bajos' | 'gastos_altos' | 'nuevo_gasto' | 'pagos_pendientes' | 'asistencia_baja';
  prioridad: 'baja' | 'media' | 'alta' | 'critica';
  titulo: string;
  mensaje: string;
  cliente: number | null;
  cliente_detalle: {
    usuario: number;
    nombre: string;
    correo: string;
  } | null;
  membresia: number | null;
  membresia_detalle: {
    id: number;
    nombre: string;
    estado: string;
  } | null;
  pago: number | null;
  pago_detalle: {
    id: number;
    valor: string;
    concepto: string;
  } | null;
  gasto: number | null;
  gasto_detalle: {
    id: number;
    descripcion: string;
    valor: string;
  } | null;
  leida: boolean;
  leida_por: number | null;
  leida_por_detalle: {
    id: number;
    nombre: string;
    correo: string;
  } | null;
  leida_at: string | null;
  datos_adicionales: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** DTOs para el dashboard financiero */

export interface MetricasClientes {
  total_registrados: number;
  activos: number;
  inactivos: number;
  membresias_vencidas: number;
  nuevos_dia: number;
  nuevos_mes: number;
  por_vencer: number;
  sin_renovar: number;
}

export interface MetricasAsistencias {
  hoy: number;
  semana: number;
  mes: number;
  promedio_diario: number;
  hora_pico: string | null;
  hora_valle: string | null;
  top_clientes: Array<{
    cliente_id: number;
    cliente__usuario__nombre: string;
    total: number;
  }>;
}

export interface MetricasFinancieras {
  ingresos: {
    dia: number;
    semana: number;
    mes: number;
    anio: number;
    pendientes_dia: number;
    pendientes_mes: number;
    por_concepto: Array<{
      concepto: string;
      total: string;
      count: number;
    }>;
  };
  gastos: {
    dia: number;
    mes: number;
    anio: number;
    por_categoria: Array<{
      categoria__nombre: string;
      categoria__color: string;
      total: string;
      count: number;
    }>;
  };
  ganancia_neta: {
    dia: number;
    mes: number;
    anio: number;
  };
}

export interface MetricasMembresias {
  activas: number;
  vencidas: number;
  por_vencer: number;
  nuevas_mes: number;
  renovaciones_mes: number;
  canceladas: number;
  ingresos_membresias: number;
  por_tipo: Record<string, number>;
}

export interface GraficaIngresosVsGastos {
  mes: string;
  ingresos: number;
  gastos: number;
  ganancia: number;
}

export interface GraficaGananciasMensuales {
  mes: string;
  ganancia: number;
}

export interface GraficaAsistenciasPorDia {
  fecha: string;
  total: number;
}

export interface GraficaCrecimientoClientes {
  mes: string;
  nuevos: number;
}

export interface GraficaDistribucionMembresias {
  tipo: string;
  count: number;
}

export interface GraficaClientesActivosVsInactivos {
  activos: number;
  inactivos: number;
}

export interface GraficaHorarioAsistencia {
  hora: string;
  total: number;
}

export interface DashboardFinancieroData {
  metricas_clientes: MetricasClientes;
  metricas_asistencias: MetricasAsistencias;
  metricas_financieras: MetricasFinancieras;
  metricas_membresias: MetricasMembresias;
  graficas: {
    ingresos_vs_gastos: GraficaIngresosVsGastos[];
    ganancias_mensuales: GraficaGananciasMensuales[];
    asistencias_por_dia: GraficaAsistenciasPorDia[];
    crecimiento_clientes: GraficaCrecimientoClientes[];
    distribucion_membresias: GraficaDistribucionMembresias[];
    clientes_activos_vs_inactivos: GraficaClientesActivosVsInactivos;
    horarios_asistencia: GraficaHorarioAsistencia[];
    periodo?: { meses: number; dias: number };
  };
  alertas_recientes: Alerta[];
}

/** Filtros para listados */
export interface FiltrosFecha {
  fecha_desde?: string;
  fecha_hasta?: string;
}

export interface FiltrosPago {
  search?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  cliente?: number;
  concepto?: string;
  estado?: string;
  metodo_pago?: number;
}

export interface FiltrosGasto {
  search?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  categoria?: number;
  estado?: string;
  metodo_pago?: number;
}

export interface FiltrosMembresia {
  estado?: string;
  tipo?: string;
  entrenador_asignado?: number;
}

export interface FiltrosAlerta {
  tipo?: string;
  prioridad?: string;
  leida?: boolean;
  cliente?: number;
}

/** Estadísticas de endpoints */
export interface EstadisticasPago {
  total_ingresos: number;
  total_pendientes: number;
  count_completados: number;
  count_pendientes: number;
  por_concepto: Array<{ concepto: string; total: string; count: number }>;
  por_metodo: Array<{ metodo_pago__nombre: string; total: string; count: number }>;
}

export interface EstadisticasGasto {
  total_gastos: number;
  count: number;
  por_categoria: Array<{ categoria__nombre: string; categoria__color: string; total: string; count: number }>;
  por_estado: Array<{ estado: string; total: string; count: number }>;
}

export interface EstadisticasMembresia {
  total: number;
  por_estado: Record<string, number>;
  por_tipo: Record<string, number>;
  proximas_a_vencer: number;
  vencidas: number;
}

export interface EstadisticasAlerta {
  total: number;
  no_leidas: number;
  por_tipo: Record<string, number>;
  por_prioridad: Record<string, number>;
}

/** Datos y umbrales de alertas del gimnasio de la sesión (GET/PATCH /gimnasio/). */
export interface ConfiguracionGimnasio {
  id: number;
  nombre: string;
  codigo: string;
  nit: string | null;
  ciudad: string | null;
  direccion: string | null;
  telefono: string | null;
  correo: string | null;
  dias_inactividad_alerta: number;
  limite_gastos_mensual: string | null;
  porcentaje_caida_ingresos: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
