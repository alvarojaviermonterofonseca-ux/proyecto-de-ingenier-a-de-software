import type { ApiErrorPayload } from './api.models';

export class ApiError extends Error {
  readonly status: number;
  readonly code: number;
  readonly details: unknown;

  constructor(status: number, message: string, code = status, details: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  static from(status: number, payload: unknown): ApiError {
    if (isApiErrorPayload(payload)) {
      return new ApiError(
        status,
        payload.error.mensaje,
        payload.error.codigo,
        payload.error.detalles,
      );
    }
    return new ApiError(status, defaultMessage(status), status, payload);
  }

  fieldErrors(): Record<string, string> {
    const details = this.details;
    if (!details || typeof details !== 'object' || Array.isArray(details)) {
      return {};
    }
    const result: Record<string, string> = {};
    for (const [field, value] of Object.entries(details as Record<string, unknown>)) {
      result[field] = flattenError(value);
    }
    return result;
  }
}

function isApiErrorPayload(value: unknown): value is ApiErrorPayload {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as { error?: unknown };
  if (!candidate.error || typeof candidate.error !== 'object') {
    return false;
  }
  const error = candidate.error as { mensaje?: unknown };
  return typeof error.mensaje === 'string';
}

function flattenError(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(flattenError).filter(Boolean).join(' ');
  }
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>)
      .map(flattenError)
      .filter(Boolean)
      .join(' ');
  }
  return String(value ?? '');
}

export function defaultMessage(status: number): string {
  const messages: Record<number, string> = {
    400: 'La solicitud contiene datos no válidos.',
    401: 'La sesión expiró. Inicia sesión nuevamente.',
    403: 'No tienes permiso para realizar esta operación.',
    404: 'No se encontró el recurso solicitado.',
    409: 'La operación entra en conflicto con otro registro.',
    429: 'Demasiadas solicitudes. Intenta de nuevo más tarde.',
    500: 'Ocurrió un error interno. Intenta de nuevo.',
  };
  return messages[status] ?? 'No se pudo completar la solicitud.';
}
