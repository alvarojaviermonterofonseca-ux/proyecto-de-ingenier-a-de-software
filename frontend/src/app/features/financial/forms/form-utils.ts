import { ApiError } from '../../../core/api/api-error';

/** Mensaje legible de un error de la API, con el detalle por campo si lo hay. */
export function describirError(error: unknown, respaldo: string): string {
  if (!(error instanceof ApiError)) {
    return respaldo;
  }
  const campos = Object.values(error.fieldErrors()).filter(Boolean);
  return campos.length > 0 ? campos.join(' ') : error.message;
}

/** Suma meses a una fecha `AAAA-MM-DD`; si el día no existe usa el último del mes. */
export function sumarMeses(fechaIso: string, meses: number): string {
  const [anio, mes, dia] = fechaIso.split('-').map(Number);
  if (!anio || !mes || !dia) {
    return fechaIso;
  }
  const indice = mes - 1 + meses;
  const anioDestino = anio + Math.floor(indice / 12);
  const mesDestino = ((indice % 12) + 12) % 12;
  const ultimoDia = new Date(anioDestino, mesDestino + 1, 0).getDate();
  const pad = (parte: number) => String(parte).padStart(2, '0');
  return `${anioDestino}-${pad(mesDestino + 1)}-${pad(Math.min(dia, ultimoDia))}`;
}

/** Suma días a una fecha `AAAA-MM-DD` sin pasar por UTC. */
export function sumarDias(fechaIso: string, dias: number): string {
  const [anio, mes, dia] = fechaIso.split('-').map(Number);
  if (!anio || !mes || !dia) {
    return fechaIso;
  }
  const fecha = new Date(anio, mes - 1, dia + dias);
  const pad = (parte: number) => String(parte).padStart(2, '0');
  return `${fecha.getFullYear()}-${pad(fecha.getMonth() + 1)}-${pad(fecha.getDate())}`;
}
