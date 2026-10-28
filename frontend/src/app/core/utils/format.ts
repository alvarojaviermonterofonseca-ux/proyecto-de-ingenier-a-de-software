const dateFormatter = new Intl.DateTimeFormat('es-CO', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

const dateTimeFormatter = new Intl.DateTimeFormat('es-CO', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const timeFormatter = new Intl.DateTimeFormat('es-CO', {
  hour: '2-digit',
  minute: '2-digit',
});

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  const date = dateOnly(value) ?? new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return dateFormatter.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return dateTimeFormatter.format(date);
}

export function formatTime(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  if (/^\d{2}:\d{2}/.test(value)) {
    return value.slice(0, 5);
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : timeFormatter.format(date);
}

export function relativeDate(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  const diff = date.getTime() - Date.now();
  const minutes = Math.round(diff / 60000);
  if (Math.abs(minutes) < 60) {
    return new Intl.RelativeTimeFormat('es-CO', { numeric: 'auto' }).format(
      minutes,
      'minute',
    );
  }
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) {
    return new Intl.RelativeTimeFormat('es-CO', { numeric: 'auto' }).format(
      hours,
      'hour',
    );
  }
  const days = Math.round(hours / 24);
  return new Intl.RelativeTimeFormat('es-CO', { numeric: 'auto' }).format(
    days,
    'day',
  );
}

export function dateInput(value: string | null | undefined): string {
  if (!value) {
    return '';
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    return value.slice(0, 10);
  }
  return localDateString(new Date(value));
}

export function dateTimeInput(value: string | null | undefined): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function toIso(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function todayInput(): string {
  return localDateString(new Date());
}

export function initials(name: string | null | undefined): string {
  if (!name) {
    return '?';
  }
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('');
}

export function humanize(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  const text = value.replaceAll('-', ' ').replaceAll('_', ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const MEAL_TYPES: Record<string, string> = {
  desayuno: 'Desayuno',
  almuerzo: 'Almuerzo',
  cena: 'Cena',
  merienda: 'Merienda',
  otra: 'Otra',
};

export const ATTENDANCE_METHODS: Record<string, string> = {
  qr: 'Código QR',
  facial: 'Reconocimiento facial',
  manual: 'Manual',
};

export const NOTIFICATION_TYPES: Record<string, string> = {
  recordatorio_asistencia: 'Recordatorio de asistencia',
  recordatorio_comida: 'Recordatorio de comida',
  alerta: 'Alerta',
  sistema: 'Sistema',
};

export const NOTIFICATION_STATES: Record<string, string> = {
  pendiente: 'Pendiente',
  enviada: 'Enviada',
  fallida: 'Fallida',
  cancelada: 'Cancelada',
};

export const ADMIN_LEVELS: Record<string, string> = {
  operativo: 'Operativo',
  gestion: 'Gestión',
  total: 'Total',
};

function dateOnly(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function localDateString(date: Date): string {
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
