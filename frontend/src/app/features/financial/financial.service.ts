import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiClient, QueryParams } from '../../core/api/api-client.service';
import {
  MetodoPago,
  CategoriaGasto,
  Pago,
  Gasto,
  Membresia,
  Alerta,
  PaginatedResponse,
  DashboardFinancieroData,
  EstadisticasPago,
  EstadisticasGasto,
  EstadisticasMembresia,
  EstadisticasAlerta,
  FiltrosPago,
  FiltrosGasto,
  FiltrosMembresia,
  FiltrosAlerta,
} from './financial.models';

@Injectable({ providedIn: 'root' })
export class FinancialService {
  private readonly api = inject(ApiClient);

  // =========================================================================
  // DASHBOARD FINANCIERO
  // =========================================================================

  getDashboard(periodo: { meses?: number; dias?: number } = {}): Observable<DashboardFinancieroData> {
    return this.api.get<DashboardFinancieroData>('dashboard/', periodo as QueryParams);
  }

  // =========================================================================
  // MÉTODOS DE PAGO
  // =========================================================================

  getMetodosPago(params: QueryParams = {}): Observable<PaginatedResponse<MetodoPago>> {
    return this.api.get<PaginatedResponse<MetodoPago>>('metodos-pago/', params);
  }

  getAllMetodosPago(): Observable<MetodoPago[]> {
    return this.api.getAll<MetodoPago>('metodos-pago/');
  }

  getMetodoPago(id: number): Observable<MetodoPago> {
    return this.api.get<MetodoPago>(`metodos-pago/${id}/`);
  }

  createMetodoPago(data: Partial<MetodoPago>): Observable<MetodoPago> {
    return this.api.post<MetodoPago>('metodos-pago/', data);
  }

  updateMetodoPago(id: number, data: Partial<MetodoPago>): Observable<MetodoPago> {
    return this.api.patch<MetodoPago>(`metodos-pago/${id}/`, data);
  }

  deleteMetodoPago(id: number): Observable<void> {
    return this.api.delete<void>(`metodos-pago/${id}/`);
  }

  exportMetodosPago(params: QueryParams = {}): Observable<Blob> {
    return this.exportar('metodos-pago', params);
  }

  // =========================================================================
  // CATEGORÍAS DE GASTO
  // =========================================================================

  getCategoriasGasto(params: QueryParams = {}): Observable<PaginatedResponse<CategoriaGasto>> {
    return this.api.get<PaginatedResponse<CategoriaGasto>>('categorias-gasto/', params);
  }

  getAllCategoriasGasto(): Observable<CategoriaGasto[]> {
    return this.api.getAll<CategoriaGasto>('categorias-gasto/');
  }

  getCategoriaGasto(id: number): Observable<CategoriaGasto> {
    return this.api.get<CategoriaGasto>(`categorias-gasto/${id}/`);
  }

  createCategoriaGasto(data: Partial<CategoriaGasto>): Observable<CategoriaGasto> {
    return this.api.post<CategoriaGasto>('categorias-gasto/', data);
  }

  updateCategoriaGasto(id: number, data: Partial<CategoriaGasto>): Observable<CategoriaGasto> {
    return this.api.patch<CategoriaGasto>(`categorias-gasto/${id}/`, data);
  }

  deleteCategoriaGasto(id: number): Observable<void> {
    return this.api.delete<void>(`categorias-gasto/${id}/`);
  }

  // =========================================================================
  // PAGOS / INGRESOS
  // =========================================================================

  getPagos(params: QueryParams = {}): Observable<PaginatedResponse<Pago>> {
    return this.api.get<PaginatedResponse<Pago>>('pagos/', params);
  }

  getPago(id: number): Observable<Pago> {
    return this.api.get<Pago>(`pagos/${id}/`);
  }

  createPago(data: Partial<Pago>): Observable<Pago> {
    return this.api.post<Pago>('pagos/', data);
  }

  updatePago(id: number, data: Partial<Pago>): Observable<Pago> {
    return this.api.patch<Pago>(`pagos/${id}/`, data);
  }

  deletePago(id: number): Observable<void> {
    return this.api.delete<void>(`pagos/${id}/`);
  }

  getEstadisticasPagos(params: FiltrosPago = {}): Observable<EstadisticasPago> {
    return this.api.get<EstadisticasPago>('pagos/estadisticas/', params as QueryParams);
  }

  exportPagos(params: FiltrosPago = {}): Observable<Blob> {
    return this.exportar('pagos', params as QueryParams);
  }

  // =========================================================================
  // GASTOS
  // =========================================================================

  getGastos(params: QueryParams = {}): Observable<PaginatedResponse<Gasto>> {
    return this.api.get<PaginatedResponse<Gasto>>('gastos/', params);
  }

  getGasto(id: number): Observable<Gasto> {
    return this.api.get<Gasto>(`gastos/${id}/`);
  }

  createGasto(data: Partial<Gasto>): Observable<Gasto> {
    return this.api.post<Gasto>('gastos/', data);
  }

  updateGasto(id: number, data: Partial<Gasto>): Observable<Gasto> {
    return this.api.patch<Gasto>(`gastos/${id}/`, data);
  }

  deleteGasto(id: number): Observable<void> {
    return this.api.delete<void>(`gastos/${id}/`);
  }

  getEstadisticasGastos(params: FiltrosGasto = {}): Observable<EstadisticasGasto> {
    return this.api.get<EstadisticasGasto>('gastos/estadisticas/', params as QueryParams);
  }

  exportGastos(params: FiltrosGasto = {}): Observable<Blob> {
    return this.exportar('gastos', params as QueryParams);
  }

  // =========================================================================
  // MEMBRESÍAS
  // =========================================================================

  getMembresias(params: QueryParams = {}): Observable<PaginatedResponse<Membresia>> {
    return this.api.get<PaginatedResponse<Membresia>>('membresias/', params);
  }

  getMembresia(id: number): Observable<Membresia> {
    return this.api.get<Membresia>(`membresias/${id}/`);
  }

  createMembresia(data: Partial<Membresia>): Observable<Membresia> {
    return this.api.post<Membresia>('membresias/', data);
  }

  updateMembresia(id: number, data: Partial<Membresia>): Observable<Membresia> {
    return this.api.patch<Membresia>(`membresias/${id}/`, data);
  }

  deleteMembresia(id: number): Observable<void> {
    return this.api.delete<void>(`membresias/${id}/`);
  }

  renovarMembresia(id: number, tipo: string, meses: number): Observable<Membresia> {
    return this.api.post<Membresia>(`membresias/${id}/renovar/`, { tipo, meses });
  }

  congelarMembresia(id: number, dias: number): Observable<Membresia> {
    return this.api.post<Membresia>(`membresias/${id}/congelar/`, { dias });
  }

  activarMembresia(id: number): Observable<Membresia> {
    return this.api.post<Membresia>(`membresias/${id}/activar/`, {});
  }

  getEstadisticasMembresias(params: FiltrosMembresia = {}): Observable<EstadisticasMembresia> {
    return this.api.get<EstadisticasMembresia>('membresias/estadisticas/', params as QueryParams);
  }

  exportMembresias(params: FiltrosMembresia = {}): Observable<Blob> {
    return this.exportar('membresias', params as QueryParams);
  }

  // =========================================================================
  // ALERTAS
  // =========================================================================

  getAlertas(params: QueryParams = {}): Observable<PaginatedResponse<Alerta>> {
    return this.api.get<PaginatedResponse<Alerta>>('alertas/', params);
  }

  getAlerta(id: number): Observable<Alerta> {
    return this.api.get<Alerta>(`alertas/${id}/`);
  }

  marcarAlertaLeida(id: number): Observable<Alerta> {
    return this.api.post<Alerta>(`alertas/${id}/marcar-leida/`, {});
  }

  marcarTodasAlertasLeidas(): Observable<{ mensaje: string; cantidad: number }> {
    return this.api.post<{ mensaje: string; cantidad: number }>('alertas/marcar-todas-leidas/', {});
  }

  getEstadisticasAlertas(params: FiltrosAlerta = {}): Observable<EstadisticasAlerta> {
    return this.api.get<EstadisticasAlerta>('alertas/estadisticas/', params as QueryParams);
  }

  exportAlertas(params: FiltrosAlerta = {}): Observable<Blob> {
    return this.exportar('alertas', params as QueryParams);
  }

  // =========================================================================
  // EXPORTACIÓN
  // =========================================================================

  /** Descarga el CSV de un recurso con los mismos filtros de su listado. */
  exportar(recurso: string, params: QueryParams = {}): Observable<Blob> {
    return this.api.blob(`${recurso}/exportar/`, params);
  }

  /** Reporte administrativo en Excel o PDF (`reportes/<tipo>/`). */
  descargarReporte(
    tipo: string,
    formato: 'xlsx' | 'pdf',
    rango: { fecha_desde?: string; fecha_hasta?: string },
  ): Observable<Blob> {
    const params: QueryParams = { formato };
    if (rango.fecha_desde) params['fecha_desde'] = rango.fecha_desde;
    if (rango.fecha_hasta) params['fecha_hasta'] = rango.fecha_hasta;
    return this.api.blob(`reportes/${tipo}/`, params);
  }

  /** Entrega un archivo ya descargado al navegador para que lo guarde. */
  guardarArchivo(blob: Blob, nombre: string): void {
    const url = window.URL.createObjectURL(blob);
    const enlace = document.createElement('a');
    enlace.href = url;
    enlace.download = nombre;
    enlace.click();
    window.URL.revokeObjectURL(url);
  }

  // =========================================================================
  // UTILIDADES
  // =========================================================================

  /** Formatea un valor numérico como moneda COP */
  formatearMoneda(valor: number | string): string {
    const num = typeof valor === 'string' ? parseFloat(valor) : valor;
    return new Intl.NumberFormat('es-CO', {
      style: 'currency',
      currency: 'COP',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  }

  /** Formatea una fecha en formato DD/MM/YYYY */
  formatearFecha(fecha: string): string {
    // Una fecha sin hora ("2026-11-15") se interpreta como UTC y en Colombia
    // se mostraría el día anterior: se construye en hora local.
    const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fecha);
    const valor = partes
      ? new Date(Number(partes[1]), Number(partes[2]) - 1, Number(partes[3]))
      : new Date(fecha);
    return valor.toLocaleDateString('es-CO', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  }

  /** Formatea una fecha y hora en formato DD/MM/YYYY HH:mm */
  formatearFechaHora(fecha: string): string {
    return new Date(fecha).toLocaleString('es-CO', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  /** Obtiene el color para el estado de una membresía */
  getColorEstadoMembresia(estado: string): string {
    const colores: Record<string, string> = {
      activa: '#22c55e',
      por_vencer: '#f59e0b',
      vencida: '#ef4444',
      cancelada: '#64748b',
      congelada: '#3b82f6',
    };
    return colores[estado] || '#64748b';
  }

  /** Obtiene el color para la prioridad de una alerta */
  getColorPrioridadAlerta(prioridad: string): string {
    const colores: Record<string, string> = {
      baja: '#64748b',
      media: '#3b82f6',
      alta: '#f59e0b',
      critica: '#ef4444',
    };
    return colores[prioridad] || '#64748b';
  }

  /** Obtiene el icono para el concepto de un pago */
  getIconoConcepto(concepto: string): string {
    const iconos: Record<string, string> = {
      membresia: 'id-card',
      renovacion: 'refresh-cw',
      matricula: 'user-plus',
      entrenamiento_personal: 'dumbbell',
      plan_alimentacion: 'salad',
      producto: 'package',
      otro: 'help-circle',
    };
    return iconos[concepto] || 'help-circle';
  }

  /** Obtiene el label legible para el concepto de un pago */
  getLabelConcepto(concepto: string): string {
    const labels: Record<string, string> = {
      membresia: 'Membresía',
      renovacion: 'Renovación',
      matricula: 'Matrícula',
      entrenamiento_personal: 'Entrenamiento personal',
      plan_alimentacion: 'Plan de alimentación',
      producto: 'Producto',
      otro: 'Otro',
    };
    return labels[concepto] || concepto;
  }

  /** Obtiene el label legible para el estado de un pago */
  getLabelTipoMembresia(tipo: string): string {
    const labels: Record<string, string> = {
      mensual: 'Mensual',
      trimestral: 'Trimestral',
      semestral: 'Semestral',
      anual: 'Anual',
      visita: 'Visita única',
      personalizada: 'Personalizada',
    };
    return labels[tipo] || tipo;
  }

  getLabelEstadoPago(estado: string): string {
    const labels: Record<string, string> = {
      completado: 'Completado',
      pendiente: 'Pendiente',
      fallido: 'Fallido',
      reembolsado: 'Reembolsado',
    };
    return labels[estado] || estado;
  }

  /** Obtiene el label legible para el estado de un gasto */
  getLabelEstadoGasto(estado: string): string {
    const labels: Record<string, string> = {
      registrado: 'Registrado',
      aprobado: 'Aprobado',
      pagado: 'Pagado',
      cancelado: 'Cancelado',
    };
    return labels[estado] || estado;
  }

  /** Obtiene el label legible para el tipo de alerta */
  getLabelTipoAlerta(tipo: string): string {
    const labels: Record<string, string> = {
      membresia_por_vencer: 'Membresía por vencer',
      membresia_vencida: 'Membresía vencida',
      cliente_inactivo: 'Cliente inactivo',
      ingresos_bajos: 'Ingresos bajos',
      gastos_altos: 'Gastos altos',
      nuevo_gasto: 'Nuevo gasto',
      pagos_pendientes: 'Pagos pendientes',
      asistencia_baja: 'Asistencia baja',
    };
    return labels[tipo] || tipo;
  }

  /** Obtiene el label legible para la prioridad de una alerta */
  getLabelPrioridad(prioridad: string): string {
    const labels: Record<string, string> = {
      baja: 'Baja',
      media: 'Media',
      alta: 'Alta',
      critica: 'Crítica',
    };
    return labels[prioridad] || prioridad;
  }

  /** Formatea una fecha como tiempo relativo */
  formatRelativeTime(fecha: string): string {
    const diff = Date.now() - new Date(fecha).getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Ahora';
    if (minutes < 60) return `Hace ${minutes} min`;
    if (hours < 24) return `Hace ${hours} h`;
    if (days < 7) return `Hace ${days} d`;
    return new Date(fecha).toLocaleDateString('es-CO');
  }
}