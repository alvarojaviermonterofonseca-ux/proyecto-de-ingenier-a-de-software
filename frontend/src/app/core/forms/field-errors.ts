import type { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

import { ApiError } from '../api/api-error';

/** Mensaje en español del primer error de validación de un control. */
export function mensajeValidacion(control: AbstractControl | null | undefined): string | null {
  const errores = control?.errors;
  if (!errores) return null;
  if (errores['required']) return 'Este campo es obligatorio.';
  if (errores['email']) return 'Escribe un correo válido, por ejemplo nombre@correo.com.';
  if (errores['minlength']) {
    return `Debe tener al menos ${errores['minlength'].requiredLength} caracteres.`;
  }
  if (errores['maxlength']) {
    return `No puede tener más de ${errores['maxlength'].requiredLength} caracteres.`;
  }
  if (errores['min']) return `El valor mínimo es ${errores['min'].min}.`;
  if (errores['max']) return `El valor máximo es ${errores['max'].max}.`;
  for (const valor of Object.values(errores)) {
    if (typeof valor === 'string') return valor;
  }
  return 'Valor no válido.';
}

/**
 * Errores de campo de una respuesta 400, aplanados a ``campo → mensaje``.
 *
 * Los objetos anidados (por ejemplo ``perfil``) se aplanan con el nombre del
 * campo hijo, porque el formulario muestra esos campos al mismo nivel.
 */
export function erroresDelServidor(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const detalles = error.details;
  const resultado: Record<string, string> = {};
  const recorrer = (valor: unknown, campo: string): void => {
    if (Array.isArray(valor)) {
      const texto = valor.filter((item) => typeof item === 'string').join(' ');
      if (texto) resultado[campo] = resultado[campo] ? `${resultado[campo]} ${texto}` : texto;
      return;
    }
    if (valor && typeof valor === 'object') {
      for (const [hijo, contenido] of Object.entries(valor as Record<string, unknown>)) {
        recorrer(contenido, hijo === '__all__' || hijo === 'non_field_errors' ? campo : hijo);
      }
      return;
    }
    if (typeof valor === 'string' && valor) resultado[campo] = valor;
  };
  if (detalles && typeof detalles === 'object' && !Array.isArray(detalles)) {
    recorrer(detalles, 'general');
  }
  return resultado;
}

/** Contraseña con letras: Django rechaza las completamente numéricas. */
export const contrasenaNoNumerica: ValidatorFn = (control): ValidationErrors | null => {
  const valor = String(control.value ?? '');
  return valor && /^\d+$/.test(valor)
    ? { contrasena: 'La contraseña no puede ser solo números; combina letras y números.' }
    : null;
};

/** Fecha (yyyy-mm-dd) que no sea posterior a hoy. */
export const fechaNoFutura: ValidatorFn = (control): ValidationErrors | null => {
  const valor = String(control.value ?? '');
  if (!valor) return null;
  const hoy = new Date();
  const limite = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`;
  return valor > limite ? { fecha: 'La fecha no puede ser futura.' } : null;
};

/** Teléfono: dígitos, espacios, guiones, paréntesis y un + inicial; 7 a 15 dígitos. */
export const telefonoValido: ValidatorFn = (control): ValidationErrors | null => {
  const valor = String(control.value ?? '').trim();
  if (!valor) return null;
  const digitos = valor.replace(/\D/g, '');
  return /^\+?[\d\s()-]+$/.test(valor) && digitos.length >= 7 && digitos.length <= 15
    ? null
    : { telefono: 'Escribe un teléfono válido (solo números, entre 7 y 15 dígitos).' };
};
